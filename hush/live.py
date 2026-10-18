"""Live TV: channels extracted from IPTV playlists, kept in the database like a library."""
from __future__ import annotations

import hashlib
import re
import threading
from pathlib import Path
from urllib.parse import urlparse

import httpx

from . import epg
from .sources import playlist
from .sources.base import SourceError, enc
from .sources.http import check_url_allowed
from .sources.links import BACKEND_SCHEMES, LIVE_SCHEMES, scheme

LOGO_MAX = 600_000
PLAYABLE = LIVE_SCHEMES | BACKEND_SCHEMES | {"http", "https"}


def chan_key(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:20]


def playlist_id(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:10]


class LiveTV:
    def __init__(self, cfg, db, registry):
        self.cfg, self.db, self.registry = cfg, db, registry
        self.logo_dir = cfg.data_dir / "art" / "logos"
        self._busy: set[str] = set()
        self._lock = threading.Lock()

    # ---- playlists -----------------------------------------------------------------
    def add_playlist(self, name: str, url: str) -> dict:
        url = url.strip()
        if scheme(url) not in ("http", "https"):
            raise SourceError("A playlist address starts with http:// or https://")
        self.registry.get("url").validate(url)
        pid = playlist_id(url)
        self.db.save_playlist(pid, (name or "").strip() or urlparse(url).path.rsplit("/", 1)[-1] or url, url)
        self.sync(pid)
        self.guide_async()
        return self.db.get_playlist(pid)

    def guide_async(self) -> None:
        """Fetch the programme guide in the background; it can be large."""
        threading.Thread(target=lambda: epg.refresh(self.db, self.db.epg_urls()), name="epg", daemon=True).start()

    def import_sources(self) -> int:
        """Playlists already saved under Add a source → Web folder or links become Live TV playlists."""
        n = 0
        for src in self.registry._sources.values():
            if getattr(src, "type", "") != "http":
                continue
            for u in getattr(src, "urls", []):
                if playlist.is_playlist_path(urlparse(u["url"]).path):
                    pid = playlist_id(u["url"])
                    if not self.db.get_playlist(pid):
                        self.db.save_playlist(pid, u.get("name") or src.name, u["url"])
                        n += 1
        return n

    def sync(self, pid: str) -> int:
        """Re-read one playlist. Returns its channel count; the error is kept on the playlist."""
        pl = self.db.get_playlist(pid)
        if not pl:
            raise KeyError(pid)
        with self._lock:
            if pid in self._busy:
                return pl["channels"]
            self._busy.add(pid)
        try:
            text = self._download(pl["url"])
            if playlist.is_hls(text):
                raise SourceError("That address is a single stream, not a list of channels. Use Play a link for it.")
            rows, seen = [], set()
            for it in playlist.parse(text, base=pl["url"]):
                url = it["url"]
                if scheme(url) not in PLAYABLE or url in seen:
                    continue
                seen.add(url)
                groups = [g.strip() for g in re.split(r"[;|]", it["group"]) if g.strip()]
                rows.append((chan_key(url), it["title"] or urlparse(url).netloc, ";" + ";".join(groups) + ";" if groups else "",
                             it.get("logo") or "", url, enc(url), it.get("tvg_id") or ""))
            n = self.db.replace_channels(pid, rows)
            self.db.playlist_status(pid, n, None)
            self.db.set_playlist_epg(pid, playlist.epg_urls(text))
            return n
        except (SourceError, httpx.HTTPError) as exc:
            self.db.playlist_status(pid, None, str(exc)[:200])
            raise SourceError(f"Could not read the playlist: {exc}") from exc
        finally:
            with self._lock:
                self._busy.discard(pid)

    def sync_all(self) -> str:
        pls = self.db.list_playlists()
        if not pls:
            return "No playlists yet"
        total, failed = 0, 0
        for p in pls:
            try:
                total += self.sync(p["id"])
            except (SourceError, KeyError):
                failed += 1
        guide = epg.refresh(self.db, self.db.epg_urls())
        return (f"{total} channels from {len(pls)} playlist{'s' if len(pls) != 1 else ''}" + (f", {failed} could not be read" if failed else "")
                + (f", {guide} programmes in the guide" if guide else ""))

    def _download(self, url: str) -> str:
        data = b""
        with httpx.stream("GET", url, timeout=30, follow_redirects=True, headers={"User-Agent": "Hush/1.0"}) as r:
            r.raise_for_status()
            for chunk in r.iter_bytes():
                data += chunk
                if len(data) > playlist.MAX_BYTES:
                    break
        return data.decode("utf-8", "replace")

    # ---- logos: fetched once by the server so the page makes no third-party requests ----------------
    def logo_path(self, key: str) -> Path | None:
        ch = self.db.get_channel(key)
        if not ch or not ch["logo"]:
            return None
        dst = self.logo_dir / f"{key}.img"
        if dst.exists():
            return dst if dst.stat().st_size else None
        self.logo_dir.mkdir(parents=True, exist_ok=True)
        try:
            check_url_allowed(ch["logo"], allow_private=False)
            r = httpx.get(ch["logo"], timeout=8, follow_redirects=False, headers={"User-Agent": "Hush/1.0"})
            ok = (r.status_code == 200 and r.headers.get("content-type", "").startswith("image/")
                  and len(r.content) <= LOGO_MAX and "svg" not in r.headers.get("content-type", ""))
        except (SourceError, httpx.HTTPError):
            ok = False
        dst.write_bytes(r.content if ok else b"")
        return dst if ok else None
