"""Programme guide (XMLTV): what is on now and next for each Live TV channel.

A guide's channels are matched to yours three ways: by the playlist's tvg-id, by an id that appears inside the
channel's stream address (Pluto TV, Samsung TV Plus...), and by channel name.
"""
from __future__ import annotations

import gzip
import logging
import re
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import httpx

log = logging.getLogger("hush.epg")
MAX_DOWNLOAD = 150 * 1024 * 1024
AHEAD, BEHIND = 36 * 3600, 3600
# Free guides worth offering. The first is a good general one; the Pluto/Samsung ones match by channel id.
PRESETS = [
    {"name": "EPGShare01: United States", "url": "https://epgshare01.online/epgshare01/epg_ripper_US2.xml.gz"},
    {"name": "EPGShare01: United Kingdom", "url": "https://epgshare01.online/epgshare01/epg_ripper_UK1.xml.gz"},
    {"name": "EPGShare01: Canada", "url": "https://epgshare01.online/epgshare01/epg_ripper_CA2.xml.gz"},
    {"name": "EPGShare01: everything (large)", "url": "https://epgshare01.online/epgshare01/epg_ripper_ALL_SOURCES1.xml.gz"},
    {"name": "epg.pw: United States (large)", "url": "https://epg.pw/xmltv/epg_US.xml.gz"},
    {"name": "Pluto TV: United States", "url": "https://i.mjh.nz/PlutoTV/us.xml.gz"},
    {"name": "Samsung TV Plus: United States", "url": "https://i.mjh.nz/SamsungTVPlus/us.xml.gz"},
    {"name": "Roku Channel", "url": "https://i.mjh.nz/Roku/all.xml.gz"},
]


def parse_time(text: str) -> float | None:
    """XMLTV times look like 20261018180000 +0200."""
    text = (text or "").strip()
    try:
        dt = datetime.strptime(text[:14], "%Y%m%d%H%M%S")
        tz = text[14:].strip()
        if tz and tz[0] in "+-" and len(tz) >= 5:
            off = (int(tz[1:3]) * 3600 + int(tz[3:5]) * 60) * (1 if tz[0] == "+" else -1)
            return dt.replace(tzinfo=timezone.utc).timestamp() - off
        return dt.replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def norm(name: str) -> str:
    n = re.sub(r"[\[(].*?[\])]", " ", (name or "").lower())
    n = re.sub(r"\b(hd|fhd|uhd|sd|4k|hevc|h265|h264|1080p?|720p?|backup|alt|east|west)\b", " ", n)
    return re.sub(r"[^a-z0-9]+", "", n)


class Matcher:
    """Finds which of our channels a guide channel is."""

    def __init__(self, channels: list[dict]):
        self.by_tvg: dict[str, list[str]] = {}
        self.by_name: dict[str, list[str]] = {}
        self.by_token: dict[str, list[str]] = {}
        for c in channels:
            k = c["chan_key"]
            tvg = re.sub(r"@.*$", "", (c.get("tvg_id") or "").strip().lower())
            if tvg:
                self.by_tvg.setdefault(tvg, []).append(k)
            n = norm(c["name"])
            if len(n) >= 3:
                self.by_name.setdefault(n, []).append(k)
            for tok in set(re.findall(r"[A-Za-z0-9]{10,}", c.get("url") or "")):
                self.by_token.setdefault(tok, []).append(k)

    def find(self, gid: str, names: list[str]) -> set[str]:
        out = set(self.by_tvg.get(re.sub(r"@.*$", "", gid.lower()), []))
        out.update(self.by_token.get(gid, []))
        for n in names:
            out.update(self.by_name.get(norm(n), []))
        return out


def parse(stream, matcher: Matcher, tag: str = "", now: float | None = None) -> tuple[list[tuple], dict[str, str]]:
    """(programmes, {chan_key: guide id}) from one XMLTV stream. Only programmes of matched channels are kept."""
    now = now or time.time()
    rows: list[tuple] = []
    mapping: dict[str, str] = {}
    wanted: set[str] = set()
    names: list[str] = []
    for _, el in ET.iterparse(stream, events=("end",)):
        t = el.tag
        if t == "display-name":
            names.append((el.text or "").strip())
        elif t == "channel":
            gid = el.get("id") or ""
            keys = matcher.find(gid, names) if gid else set()
            if keys:
                wanted.add(gid)
                for k in keys:
                    mapping.setdefault(k, f"{tag}{gid}")
            names = []
            el.clear()
        elif t == "programme":
            cid = el.get("channel") or ""
            if cid in wanted:
                start, stop = parse_time(el.get("start", "")), parse_time(el.get("stop", ""))
                if start and stop and stop > now - BEHIND and start < now + AHEAD:
                    rows.append((f"{tag}{cid}", start, stop, (el.findtext("title") or "").strip()[:200],
                                 (el.findtext("desc") or "").strip()[:400]))
            el.clear()
    return rows, mapping


def _download(url: str) -> Path:
    tmp = tempfile.NamedTemporaryFile(prefix="hush-epg-", delete=False)
    size = 0
    try:
        with httpx.stream("GET", url, timeout=httpx.Timeout(60, read=120), follow_redirects=True, headers={"User-Agent": "Hush/1.0"}) as r:
            r.raise_for_status()
            for chunk in r.iter_bytes(1 << 16):
                size += len(chunk)
                if size > MAX_DOWNLOAD:
                    raise ValueError("the guide is too large")
                tmp.write(chunk)
    except Exception:
        tmp.close()
        Path(tmp.name).unlink(missing_ok=True)
        raise
    tmp.close()
    return Path(tmp.name)


def refresh(db, urls: list[str]) -> dict:
    """Download each guide, match it to the channels and keep what is on soon. Returns a summary."""
    channels = db._all("SELECT chan_key, name, url, tvg_id FROM channels")
    urls = list(dict.fromkeys(u for u in urls if u))
    if not channels or not urls:
        return {"programmes": 0, "matched": 0, "errors": []}
    matcher = Matcher(channels)
    rows: list[tuple] = []
    mapping: dict[str, str] = {}
    errors: list[str] = []
    for i, url in enumerate(urls):
        path = None
        try:
            path = _download(url)
            with open(path, "rb") as fh:
                magic = fh.read(2)
            with (gzip.open(path, "rb") if magic == b"\x1f\x8b" else open(path, "rb")) as fh:
                got_rows, got_map = parse(fh, matcher, tag=f"{i}:")
            rows += got_rows
            for k, g in got_map.items():
                mapping.setdefault(k, g)
        except (httpx.HTTPError, ValueError, ET.ParseError, OSError, EOFError) as exc:
            log.warning("guide %s: %s", url, exc)
            errors.append(f"{url.rsplit('/', 1)[-1]}: {str(exc)[:80]}")
        finally:
            if path:
                path.unlink(missing_ok=True)
    if rows:
        db.replace_programmes(rows, mapping)
    summary = {"programmes": len(rows), "matched": len(mapping), "errors": errors, "at": time.time()}
    db.set_setting("epg_status", summary)
    return summary
