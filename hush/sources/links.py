"""The built-in "Opened links" source: any link pasted into "Play a link".

http(s)            direct files, HLS/DASH, web folder listings (see HTTPSource)
smb://u:p@host/share/folder/file
ftp://u:p@host/folder/file
sftp://u:p@host/folder/file
                   handled by the real SMB / FTP / SFTP sources, built on the fly
rtmp, rtsp, udp, srt, mms ... live or network streams: played through ffmpeg
                   with no scanning, seeking or filtering (they have no fixed length)
"""
from __future__ import annotations

import threading
import time
from urllib.parse import quote, unquote, urlparse

import httpx

from .base import Entry, MediaRef, SourceError, classify, dec, enc, sort_entries
from . import playlist
from .ftp import FTPSource
from .http import HTTPSource, _url_kind, check_host, check_url_allowed
from .sftp import SFTPSource
from .smb import SMBSource

BACKEND_SCHEMES = {"smb", "ftp", "sftp"}
LIVE_SCHEMES = {"rtmp", "rtmps", "rtmpt", "rtsp", "rtsps", "rtp", "udp", "srt",
                "mms", "mmsh", "mmst", "tcp", "rist"}
MULTICAST_OK = {"udp", "rtp", "srt"}   # IPTV is commonly multicast
SUPPORTED = "http(s), smb, ftp, sftp, rtmp, rtsp, udp, srt, mms"


def scheme(url: str) -> str:
    return urlparse(url).scheme.lower()


def clean(url: str) -> str:
    """The link without any user:password, for names and messages."""
    p = urlparse(url)
    host = p.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    return p._replace(netloc=host + (f":{p.port}" if p.port else "")).geturl()


class LinkSource(HTTPSource):
    """The built-in "Opened links" source."""
    type = "link"

    def __init__(self, conf):
        super().__init__(conf)
        self._backends: dict[tuple, tuple] = {}
        self._blk = threading.Lock()
        self._plists: dict[str, tuple[float, str | None]] = {}   # url -> (fetched at, text; None = HLS)

    # ---- validation and naming -------------------------------------------
    def validate(self, url: str) -> None:
        s = scheme(url)
        if s in ("http", "https"):
            check_url_allowed(url, self.allow_private, self.allowed_hosts)
        elif s in BACKEND_SCHEMES or s in LIVE_SCHEMES:
            check_host(urlparse(url).hostname or "", self.allow_private, self.allowed_hosts,
                       allow_multicast=s in MULTICAST_OK)
        else:
            raise SourceError(f"unsupported link type {s or url!r}. Supported: {SUPPORTED}")

    _check = validate

    def display_name(self, url: str) -> str:
        p = urlparse(clean(url))
        last = unquote(p.path.rstrip("/").rsplit("/", 1)[-1])
        return last or p.netloc or url

    def _playlist_text(self, url: str) -> str | None:
        """The text of a list playlist at this URL, or None when it is an HLS stream."""
        hit = self._plists.get(url)
        if hit and time.time() - hit[0] < 60:
            return hit[1]
        self._check(url)
        try:
            with httpx.stream("GET", url, headers=self.headers, timeout=15, verify=self.verify,
                              follow_redirects=True) as r:
                r.raise_for_status()
                data = b""
                for chunk in r.iter_bytes():
                    data += chunk
                    if len(data) > playlist.MAX_BYTES:
                        break
        except httpx.HTTPError as exc:
            raise SourceError(f"could not read the playlist: {exc}") from exc
        text = data.decode("utf-8", "replace")
        value = None if playlist.is_hls(text) else text
        if len(self._plists) > 50:
            self._plists.clear()
        self._plists[url] = (time.time(), value)
        return value

    def _is_list_playlist(self, url: str) -> bool:
        return (scheme(url) in ("http", "https") and playlist.is_playlist_path(urlparse(url).path)
                and self._playlist_text(url) is not None)

    def kind_of(self, url: str) -> str:
        if scheme(url) in ("http", "https") and playlist.is_playlist_path(urlparse(url).path):
            try:
                return "dir" if self._is_list_playlist(url) else "video"
            except SourceError:
                return "dir"        # let browsing report why it failed
        s = scheme(url)
        if s in LIVE_SCHEMES:
            return "video"
        if s in BACKEND_SCHEMES:
            path = urlparse(url).path
            return "dir" if path.endswith("/") or not classify(path) else (classify(path) or "video")
        return "dir" if url.endswith("/") else (_url_kind(url) or "video")

    # ---- backends for smb / ftp / sftp -------------------------------------
    def _backend(self, url: str):
        """Return (source, path inside it, link prefix of that source's root)."""
        p = urlparse(url)
        s, host, user, pw = p.scheme.lower(), p.hostname, unquote(p.username or ""), unquote(p.password or "")
        port = p.port
        parts = [x for x in unquote(p.path).split("/") if x]
        authority = p.netloc
        if s == "smb":
            if not parts:
                raise SourceError("add the share name: smb://server/share/folder/file.mkv")
            share, rel = parts[0], "/".join(parts[1:])
            key = (s, host, port, user, pw, share)
            prefix = f"smb://{authority}/{quote(share)}"
            make = lambda: SMBSource({"id": "url", "server": host, "share": share,  # noqa: E731
                                      "username": user or None, "password": pw or None,
                                      **({"port": port} if port else {})})
        else:
            rel = "/".join(parts)
            key = (s, host, port, user, pw)
            prefix = f"{s}://{authority}"
            cls = FTPSource if s == "ftp" else SFTPSource
            make = lambda: cls({"id": "url", "host": host, "username": user, "password": pw,  # noqa: E731
                                **({"port": port} if port else {})})
        with self._blk:
            if key not in self._backends:
                if len(self._backends) >= 20:
                    for old, _, _ in self._backends.values():
                        old.close()
                    self._backends.clear()
                self._backends[key] = (make(), rel, prefix)
            backend, _, prefix = self._backends[key]
        return backend, rel, prefix

    def _wrap(self, entries: list[Entry], prefix: str) -> list[Entry]:
        out = []
        for e in entries:
            rel = dec(e.id).replace("\\", "/")
            link = f"{prefix}/{quote(rel)}" + ("/" if e.kind == "dir" else "")
            out.append(Entry(enc(link), e.name, e.kind, size=e.size, meta=e.meta))
        return sort_entries(out)

    # ---- Source API ------------------------------------------------------------
    def _entry(self, item: dict) -> Entry:
        url = item["url"]
        s = scheme(url)
        if s not in ("http", "https") and s not in BACKEND_SCHEMES and s not in LIVE_SCHEMES:
            raise SourceError(f"unsupported entry {clean(url)!r}")
        kind = self.kind_of(url) if s not in ("http", "https") else (_url_kind(url) or "video")
        live = s in LIVE_SCHEMES or playlist.is_playlist_path(urlparse(url).path)
        return Entry(enc(url), item["title"] or self.display_name(url), "video" if kind == "dir" else kind,
                     meta={"live": True} if live else {})

    def _browse_playlist(self, url: str, group: str | None) -> list[Entry]:
        items = playlist.parse(self._playlist_text(url) or "", base=url)
        groups = sorted({i["group"] for i in items if i["group"]})
        out: list[Entry] = []
        if group is None and len(groups) > 1:       # IPTV lists: one folder per group
            out = [Entry(enc(f"{url}\x00{g}"), g, "dir") for g in groups]
            items = [i for i in items if not i["group"]]
        elif group is not None:
            items = [i for i in items if i["group"] == group]
        for it in items:
            try:
                out.append(self._entry(it))
            except SourceError:
                continue                            # skip lines that are not playable links
        return out

    def browse(self, dir_id: str = "") -> list[Entry]:
        if not dir_id:
            return [Entry(enc(b["url"]), b.get("name") or self.display_name(b["url"]),
                          self.kind_of(b["url"])) for b in self.urls]
        url = dec(dir_id)
        group = None
        if "\x00" in url:
            url, group = url.split("\x00", 1)
        s = scheme(url)
        if s in ("http", "https") and playlist.is_playlist_path(urlparse(url).path):
            self.validate(url)
            if self._playlist_text(url) is not None:
                return self._browse_playlist(url, group)
            raise SourceError("this is a live stream, not a list. Play it instead.")
        if s in BACKEND_SCHEMES:
            self.validate(url)
            backend, rel, prefix = self._backend(url)
            return self._wrap(backend.browse(enc(rel) if rel else ""), prefix)
        if s in ("http", "https"):
            return super().browse(dir_id)
        raise SourceError("this kind of link can only be played, not browsed")

    def resolve(self, item_id: str) -> MediaRef:
        url = dec(item_id)
        s = scheme(url)
        self.validate(url)
        if s in LIVE_SCHEMES:
            name = self.display_name(url)
            return MediaRef(title=name, kind="video", url=url, native=True, live=True, name=name)
        if s in BACKEND_SCHEMES:
            backend, rel, _ = self._backend(url)
            return backend.resolve(enc(rel))
        return super().resolve(item_id)


class WebSource(LinkSource):
    """A "Web folder or links" source from Add a source: same abilities as Play a link, so a saved
    .m3u/.m3u8 playlist opens as a list, and smb://, ftp:// and rtmp:// entries work too."""
    type = "http"
