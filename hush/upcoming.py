"""Upcoming episodes for the shows in the library, from TVmaze (free, no key)."""
from __future__ import annotations

import logging
import time
from datetime import datetime

import httpx

from .library.providers import TVMAZE, UA, TVmazeProvider, polite_get

log = logging.getLogger("hush.upcoming")
LOOKBACK, HORIZON = 86400, 400 * 86400


def airtime(ep: dict) -> float | None:
    stamp = ep.get("airstamp")
    if stamp:
        try:
            return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    day = ep.get("airdate")
    if day:
        try:
            return datetime.strptime(day, "%Y-%m-%d").timestamp() + 20 * 3600     # no time given: assume evening
        except ValueError:
            pass
    return None


def tvmaze_id(http: httpx.Client, show: dict) -> str | None:
    ids = show.get("ids") or {}
    if ids.get("tvmaze"):
        return str(ids["tvmaze"])
    for kind, param in (("imdb", "imdb"), ("tvdb", "thetvdb")):
        if ids.get(kind):
            r = polite_get(http, f"{TVMAZE}/lookup/shows", params={param: ids[kind]})
            if r.status_code == 200:
                return str(r.json()["id"])
    hit = TVmazeProvider(http).show(show["title"], show.get("year"))
    return hit["id"] if hit else None


def refresh(db, http: httpx.Client | None = None) -> str:
    """Look up each show in the library and keep its episodes that have not aired yet (and yesterday's)."""
    http = http or httpx.Client(timeout=15, headers=UA)
    now = time.time()
    shows = db.list_shows()
    kept = lookups = 0
    for show in shows:
        try:
            sid = tvmaze_id(http, show)
            time.sleep(0.5)
            if not sid:
                continue
            if str((show.get("ids") or {}).get("tvmaze") or "") != sid:
                full = db.get_show(show["show_key"])
                full["ids"] = {**(full.get("ids") or {}), "tvmaze": sid}
                db.save_show(full)
            r = polite_get(http, f"{TVMAZE}/shows/{sid}/episodes")
            time.sleep(0.5)
            lookups += 1
            if r.status_code != 200:
                continue
            rows = []
            for ep in r.json():
                t = airtime(ep)
                if t and now - LOOKBACK <= t <= now + HORIZON and ep.get("number") is not None:
                    rows.append((show["show_key"], ep["season"], ep["number"], ep.get("name") or "", t,
                                 (ep.get("summary") or "").replace("<p>", "").replace("</p>", "").replace("<b>", "").replace("</b>", "")[:400],
                                 ep.get("runtime")))
            db.replace_upcoming(show["show_key"], rows)
            kept += len(rows)
        except httpx.HTTPError as exc:
            log.warning("upcoming for %s: %s", show.get("title"), exc)
    return f"{kept} upcoming episodes for {lookups} show{'s' if lookups != 1 else ''}"
