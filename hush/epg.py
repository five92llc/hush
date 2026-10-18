"""Programme guide (XMLTV): what is on now and next for each Live TV channel."""
from __future__ import annotations

import gzip
import io
import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx

log = logging.getLogger("hush.epg")
MAX_BYTES = 80 * 1024 * 1024
AHEAD, BEHIND = 36 * 3600, 3600


def parse_time(text: str) -> float | None:
    """XMLTV times look like 20261018180000 +0200."""
    text = (text or "").strip()
    try:
        stamp = text[:14]
        dt = datetime.strptime(stamp, "%Y%m%d%H%M%S")
        tz = text[14:].strip()
        if tz and tz[0] in "+-" and len(tz) >= 5:
            off = (int(tz[1:3]) * 3600 + int(tz[3:5]) * 60) * (1 if tz[0] == "+" else -1)
            return dt.replace(tzinfo=timezone.utc).timestamp() - off
        return dt.replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def parse(stream, wanted: set[str], now: float | None = None) -> list[tuple]:
    """(tvg_id, start, stop, title, description) for the wanted channels, from about now to a day and a half ahead."""
    now = now or time.time()
    rows = []
    for _, el in ET.iterparse(stream, events=("end",)):
        if el.tag != "programme":
            if el.tag == "channel":
                el.clear()
            continue
        cid = el.get("channel") or ""
        if cid in wanted:
            start, stop = parse_time(el.get("start", "")), parse_time(el.get("stop", ""))
            if start and stop and stop > now - BEHIND and start < now + AHEAD:
                rows.append((cid, start, stop, (el.findtext("title") or "").strip()[:200], (el.findtext("desc") or "").strip()[:400]))
        el.clear()
    return rows


def refresh(db, urls: list[str]) -> int:
    """Download each guide and keep the programmes of the channels we have. Returns how many programmes were kept."""
    wanted = {r["tvg_id"] for r in db._all("SELECT DISTINCT tvg_id FROM channels WHERE tvg_id IS NOT NULL AND tvg_id != ''")}
    if not wanted:
        return 0
    rows: list[tuple] = []
    for url in dict.fromkeys(urls):
        try:
            data = b""
            with httpx.stream("GET", url, timeout=60, follow_redirects=True, headers={"User-Agent": "Hush/1.0"}) as r:
                r.raise_for_status()
                for chunk in r.iter_bytes():
                    data += chunk
                    if len(data) > MAX_BYTES:
                        raise ValueError("the guide is too large")
            if data[:2] == b"\x1f\x8b":
                data = gzip.decompress(data)
            rows += parse(io.BytesIO(data), wanted)
        except (httpx.HTTPError, ValueError, ET.ParseError, OSError, EOFError) as exc:
            log.warning("guide %s: %s", url, exc)
    if rows:
        db.replace_programmes(rows)
    return len(rows)
