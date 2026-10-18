"""My List: the shows and movies a profile follows, with what to watch next and when new episodes air."""
from __future__ import annotations

import hashlib
import threading
import time

import httpx

from .library.providers import TVMAZE, UA, _plain, _year, polite_get
from .upcoming import airtime

STATUSES = ("watching", "planned", "completed", "dropped")
_http = httpx.Client(timeout=15, headers=UA)
_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()


def art_key(ref: str) -> str:
    return hashlib.sha1(ref.encode()).hexdigest()[:16]


def search_shows(q: str) -> list[dict]:
    r = polite_get(_http, f"{TVMAZE}/search/shows", params={"q": q})
    r.raise_for_status()
    out = []
    for x in r.json()[:10]:
        s = x["show"]
        net = (s.get("network") or s.get("webChannel") or {}).get("name") or ""
        out.append({"tvmaze_id": str(s["id"]), "title": s.get("name", ""), "year": _year(s.get("premiered")), "network": net,
                    "status": s.get("status") or "", "overview": _plain(s.get("summary"))[:200],
                    "poster_url": (s.get("image") or {}).get("original") or (s.get("image") or {}).get("medium")})
    return out


def show_info(tvmaze_id: str) -> dict:
    r = polite_get(_http, f"{TVMAZE}/shows/{tvmaze_id}")
    r.raise_for_status()
    s = r.json()
    net = (s.get("network") or s.get("webChannel") or {}).get("name") or ""
    return {"title": s.get("name", ""), "year": _year(s.get("premiered")), "network": net, "status": s.get("status") or "",
            "poster_url": (s.get("image") or {}).get("original") or (s.get("image") or {}).get("medium"),
            "imdb": (s.get("externals") or {}).get("imdb")}


def next_airing(tvmaze_id: str) -> dict:
    """The next episode of a show that is not in the library, and whether it is still running (kept for 6 hours)."""
    now = time.time()
    with _lock:
        hit = _cache.get(tvmaze_id)
        if hit and now - hit[0] < 6 * 3600:
            return hit[1]
    out: dict = {"next": None, "status": ""}
    try:
        info = polite_get(_http, f"{TVMAZE}/shows/{tvmaze_id}", params={"embed": "nextepisode"})
        if info.status_code == 200:
            j = info.json()
            out["status"] = j.get("status") or ""
            ep = (j.get("_embedded") or {}).get("nextepisode")
            if ep and airtime(ep):
                out["next"] = {"season": ep["season"], "episode": ep["number"], "title": ep.get("name") or "", "airs_at": airtime(ep)}
    except httpx.HTTPError:
        return out
    with _lock:
        _cache[tvmaze_id] = (now, out)
    return out


def library_progress(episodes: list[dict]) -> dict:
    """What is left to watch in a show: how many episodes, and which one is next."""
    eps = [e for e in episodes if e.get("season") is not None or e.get("episode") is not None]
    left = [e for e in eps if not e.get("watched")]
    nxt = next((e for e in left if e.get("position")), left[0] if left else None)    # an episode in progress comes first
    return {"episodes": len(eps), "watched": len(eps) - len(left), "unwatched": len(left),
            "next": {"media_key": nxt["media_key"], "source_id": nxt["source_id"], "item_id": nxt["item_id"], "season": nxt.get("season"),
                     "episode": nxt.get("episode"), "title": nxt.get("title") or "", "position": nxt.get("position") or 0} if nxt else None}
