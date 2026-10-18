"""HTTP(S) media: direct file links, HLS/DASH playlists and web-server
directory listings (nginx/Apache/Caddy autoindex, `python -m http.server`).

Item ids are the encoded URL, so any URL can be played ad hoc through the
built-in "url" source as well as through configured bookmarks.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from html import unescape
from urllib.parse import unquote, urljoin, urlparse

import httpx

from .base import Entry, MediaRef, Source, SourceError, classify, dec, enc, sort_entries

_HREF = re.compile(r'href\s*=\s*["\']([^"\'#?]+)["\']', re.I)
STREAM_EXT = {".m3u8": "video", ".mpd": "video"}


def _url_kind(url: str) -> str | None:
    path = urlparse(url).path.lower()
    for ext, kind in STREAM_EXT.items():
        if path.endswith(ext):
            return kind
    return classify(path)


def check_host(host: str, allow_private: bool = True, allowed_hosts: list[str] | None = None,
               allow_multicast: bool = False) -> None:
    """Basic SSRF guard. Home servers usually *want* LAN addresses, so private
    ranges are allowed by default; link-local/metadata addresses never are."""
    if not host:
        raise SourceError("the link needs a host name")
    if allowed_hosts and host not in allowed_hosts:
        raise SourceError(f"host {host} is not in allowed_hosts")
    try:
        addrs = {ai[4][0] for ai in socket.getaddrinfo(host, None)}
    except socket.gaierror:
        raise SourceError(f"cannot resolve {host}")
    for a in addrs:
        ip = ipaddress.ip_address(a.split("%")[0])
        if ip.is_link_local or ip.is_unspecified or (ip.is_multicast and not allow_multicast):
            raise SourceError("link-local / metadata addresses are blocked")
        if not allow_private and (ip.is_private or ip.is_loopback):
            raise SourceError("private addresses are disabled for this source")


def check_url_allowed(url: str, allow_private: bool = True, allowed_hosts: list[str] | None = None) -> None:
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        raise SourceError("only http(s) URLs are supported")
    check_host(p.hostname or "", allow_private, allowed_hosts)


class HTTPSource(Source):
    type = "http"

    def __init__(self, conf):
        super().__init__(conf)
        self.urls: list[dict] = conf.get("urls") or []
        self.headers: dict[str, str] = conf.get("headers") or {}
        self.allow_private = conf.get("allow_private", True)
        self.allowed_hosts = conf.get("allowed_hosts")
        self.verify = conf.get("verify_tls", True)

    def _check(self, url: str) -> None:
        check_url_allowed(url, self.allow_private, self.allowed_hosts)

    def browse(self, dir_id: str = "") -> list[Entry]:
        if not dir_id:
            out = []
            for b in self.urls:
                url = b["url"]
                kind = "dir" if url.endswith("/") else (_url_kind(url) or "video")
                out.append(Entry(enc(url), b.get("name") or url, kind))
            return out
        base = dec(dir_id)
        self._check(base)
        try:
            r = httpx.get(base, headers=self.headers, timeout=15, verify=self.verify,
                          follow_redirects=True)
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise SourceError(f"listing failed: {exc}") from exc
        listing = str(r.url)
        seen, out = set(), []
        for href in _HREF.findall(r.text):
            full = urljoin(listing, unescape(href))
            # Only descend: ignore parent links, absolute links elsewhere, sort links.
            if full in seen or full == listing or not full.startswith(listing):
                continue
            seen.add(full)
            name = unquote(full[len(listing):]).rstrip("/") or full
            if full.endswith("/"):
                out.append(Entry(enc(full), name, "dir"))
            elif (kind := _url_kind(full)):
                out.append(Entry(enc(full), name, kind))
        return sort_entries(out)

    def resolve(self, item_id: str) -> MediaRef:
        url = dec(item_id)
        self._check(url)
        size = None
        try:
            h = httpx.head(url, headers=self.headers, timeout=10, verify=self.verify,
                           follow_redirects=True)
            if h.status_code < 400 and h.headers.get("content-length"):
                size = int(h.headers["content-length"])
            url = str(h.url)
        except httpx.HTTPError:
            pass
        name = unquote(urlparse(url).path.rsplit("/", 1)[-1]) or url
        return MediaRef(title=name.rsplit(".", 1)[0], kind=_url_kind(url) or "video",
                        url=url, headers=dict(self.headers), size=size, name=name)
