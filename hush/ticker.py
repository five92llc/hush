"""Data for the top bar panel: sports scores (ESPN), headlines (any RSS feed), a photo of the day (NASA) and the server's health."""
from __future__ import annotations

import os
import shutil
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

UA = {"User-Agent": "Hush/1.0 (self-hosted media player)"}
LEAGUES = {"nfl": ("football", "nfl", "NFL"), "nba": ("basketball", "nba", "NBA"), "mlb": ("baseball", "mlb", "MLB"), "nhl": ("hockey", "nhl", "NHL"),
           "epl": ("soccer", "eng.1", "Premier League"), "mls": ("soccer", "usa.1", "MLS"), "wnba": ("basketball", "wnba", "WNBA"),
           "ncaaf": ("football", "college-football", "College football"), "ncaam": ("basketball", "mens-college-basketball", "College basketball")}
DEFAULT_RSS = "https://feeds.bbci.co.uk/news/rss.xml"
_cache: dict[str, tuple[float, object]] = {}


def _cached(key: str, ttl: float, make):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    value = make()
    _cache[key] = (time.time() if value else time.time() - ttl + min(ttl, 600), value)       # a failure is tried again in 10 minutes at most
    return value


def scores(leagues: list[str], client: httpx.Client | None = None) -> list[dict]:
    """Games from the chosen leagues: live ones first, then finished, then the ones still to come."""
    out = []
    for lg in [x for x in leagues if x in LEAGUES][:6]:
        sport, slug, label = LEAGUES[lg]

        def make(sport=sport, slug=slug):
            r = (client or httpx).get(f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{slug}/scoreboard", headers=UA, timeout=10)
            r.raise_for_status()
            return r.json()
        try:
            data = _cached(f"sc:{lg}", 60, make)
        except (httpx.HTTPError, ValueError):
            continue
        for e in data.get("events", []):
            try:
                comp = e["competitions"][0]
                teams = {c["homeAway"]: c for c in comp["competitors"]}
                st = e["status"]["type"]
                out.append({"league": label, "state": st.get("state", "pre"), "detail": st.get("shortDetail", ""), "date": e.get("date", ""),
                            "away": teams["away"]["team"].get("abbreviation", "?"), "home": teams["home"]["team"].get("abbreviation", "?"),
                            "away_score": teams["away"].get("score", ""), "home_score": teams["home"].get("score", "")})
            except (KeyError, IndexError, TypeError):
                continue
    order = {"in": 0, "post": 1, "pre": 2}
    out.sort(key=lambda g: (order.get(g["state"], 3), g["date"] if g["state"] == "pre" else ""))
    return out[:24]


def headlines(url: str, client: httpx.Client | None = None) -> list[dict]:
    """The newest items of an RSS or Atom feed: [{title, source}]."""
    url = (url or DEFAULT_RSS).strip()
    if not url.startswith(("http://", "https://")):
        return []

    def make():
        r = (client or httpx).get(url, headers=UA, timeout=10, follow_redirects=True)
        r.raise_for_status()
        if len(r.content) > 3_000_000 or b"<!ENTITY" in r.content[:20000]:
            return []
        root = ET.fromstring(r.content)
        source = (root.findtext("./channel/title") or root.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
        items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
        out = []
        for it in items[:15]:
            t = (it.findtext("title") or it.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
            if t:
                out.append({"title": t[:160], "source": source[:40]})
        return out
    try:
        return _cached(f"rss:{url}", 600, make)
    except (httpx.HTTPError, ET.ParseError, ValueError):
        return []


def photo(dest: Path, client: httpx.Client | None = None) -> dict | None:
    """NASA's astronomy picture of the day: its title, saved as a small picture next to the other caches. None when today's is a video."""
    def make():
        c = client or httpx
        r = c.get("https://api.nasa.gov/planetary/apod", params={"api_key": os.environ.get("NASA_API_KEY", "DEMO_KEY")}, headers=UA, timeout=15)
        r.raise_for_status()
        j = r.json()
        if j.get("media_type") != "image" or not j.get("url"):
            return None
        img = c.get(j["url"], headers=UA, timeout=30, follow_redirects=True)
        img.raise_for_status()
        if len(img.content) > 15_000_000:
            return None
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(img.content)
        return {"title": str(j.get("title", ""))[:120], "date": j.get("date", "")}
    try:
        return _cached("apod", 6 * 3600, make)
    except (httpx.HTTPError, ValueError, OSError):
        return None


def health(data_dir: Path) -> dict:
    """Load, memory and free disk space of the machine Hush runs on."""
    out: dict = {"cpus": os.cpu_count() or 1}
    try:
        out["load"] = round(os.getloadavg()[0], 2)
    except OSError:
        out["load"] = None
    try:
        info = {k: int(v.split()[0]) for k, v in (ln.split(":", 1) for ln in Path("/proc/meminfo").read_text().splitlines() if ":" in ln)}
        out["mem_pct"] = round(100 * (1 - info["MemAvailable"] / info["MemTotal"]))
    except (OSError, KeyError, ValueError):
        out["mem_pct"] = None
    try:
        u = shutil.disk_usage(data_dir)
        out["disk_free_gb"] = round(u.free / 1e9, 1)
        out["disk_pct"] = round(100 * u.used / u.total)
    except OSError:
        out["disk_free_gb"] = out["disk_pct"] = None
    return out
