"""M3U / M3U8 / PLS playlists (IPTV lists, music lists, lists of files).

An .m3u8 can also be an HLS *stream* (segments, #EXT-X-... tags). That is played
as one video; anything else is a list of items that is browsed like a folder.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

PLAYLIST_EXT = (".m3u", ".m3u8", ".pls")
MAX_BYTES = 30 * 1024 * 1024      # the big public IPTV lists are around 10 MB
_QUOTED = re.compile(r'"[^"]*"')
_ATTR = re.compile(r'([\w-]+)\s*=\s*"([^"]*)"')


def is_playlist_path(path: str) -> bool:
    return path.lower().split("?")[0].endswith(PLAYLIST_EXT)


def is_hls(text: str) -> bool:
    return any(line.startswith("#EXT-X-") for line in text.splitlines())


def epg_urls(text: str) -> list[str]:
    """Programme-guide addresses an IPTV list advertises on its first line (url-tvg / x-tvg-url)."""
    for raw in text.lstrip("\ufeff").splitlines()[:5]:
        if raw.strip().upper().startswith("#EXTM3U"):
            attrs = dict(_ATTR.findall(raw))
            val = attrs.get("url-tvg") or attrs.get("x-tvg-url") or ""
            return [u.strip() for u in val.split(",") if u.strip().lower().startswith(("http://", "https://"))]
    return []


def parse(text: str, base: str | None = None) -> list[dict]:
    """Return [{title, url, group}] in file order. Relative entries are joined to ``base``."""
    text = text.lstrip("﻿")
    if text.lstrip().lower().startswith("[playlist]"):
        return _parse_pls(text, base)
    out: list[dict] = []
    title, group, logo, tvg_id = "", "", "", ""
    sticky_group = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.upper().startswith("#EXTINF"):
            attrs = dict(_ATTR.findall(line))
            _, _, tail = _QUOTED.sub('""', line).partition(",")
            title = tail.strip() or attrs.get("tvg-name", "")
            group = attrs.get("group-title", "")
            logo, tvg_id = attrs.get("tvg-logo", ""), attrs.get("tvg-id", "")
        elif line.upper().startswith("#EXTGRP:"):
            sticky_group = line.split(":", 1)[1].strip()
        elif not line.startswith("#"):
            out.append({"title": title, "url": urljoin(base, line) if base else line,
                        "group": group or sticky_group, "logo": logo, "tvg_id": tvg_id})
            title, group, logo, tvg_id = "", "", "", ""
    return out


def _parse_pls(text: str, base: str | None) -> list[dict]:
    files: dict[str, str] = {}
    titles: dict[str, str] = {}
    for line in text.splitlines():
        key, _, val = line.strip().partition("=")
        low = key.lower()
        if low.startswith("file"):
            files[low[4:]] = val.strip()
        elif low.startswith("title"):
            titles[low[5:]] = val.strip()
    return [{"title": titles.get(n, ""), "url": urljoin(base, u) if base else u, "group": ""}
            for n, u in sorted(files.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0)]
