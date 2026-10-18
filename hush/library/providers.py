"""Where movie and show details come from.

* TMDB   - best data; needs a free API key (themoviedb.org/settings/api)
* Cinemeta - posters, summaries and episodes for movies and shows, no key (the catalogue Stremio uses)
* Wikipedia - movies, no key
* TVmaze - shows and episodes, no key
"""
from __future__ import annotations

import html
import re
import time
from difflib import SequenceMatcher
from urllib.parse import quote

import httpx

UA = {"User-Agent": "Hush/1.0 (self-hosted media player)"}
TMDB = "https://api.themoviedb.org/3"
TMDB_IMG = "https://image.tmdb.org/t/p/w500"
TVMAZE = "https://api.tvmaze.com"
# Posters are only ever fetched from these hosts.
CINEMETA = "https://v3-cinemeta.strem.io"
IMAGE_HOSTS = ("image.tmdb.org", "upload.wikimedia.org", "static.tvmaze.com",
               "m.media-amazon.com", "images.metahub.space", "episodes.metahub.space")


def polite_get(client: httpx.Client, url: str, retries: int = 3, **kw) -> httpx.Response:
    """GET that waits and retries when a free service says "slow down" (429/503)."""
    for attempt in range(retries + 1):
        r = client.get(url, **kw)
        if r.status_code not in (429, 503) or attempt == retries:
            return r
        try:
            wait = float(r.headers.get("retry-after", ""))
        except ValueError:
            wait = 2.0 * (attempt + 1)
        time.sleep(min(wait, 20.0))
    return r


def shorten(text: str, limit: int = 600) -> str:
    """Cut a long summary at a sentence end, so it reads as a blurb."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return cut[:end + 1] if end > limit * 0.4 else cut.rstrip() + "…"


def norm(text: str) -> str:
    t = re.sub(r"[^a-z0-9 ]", "", (text or "").lower().replace("&", " and "))
    t = re.sub(r"^(the|a|an) ", "", t.strip())
    return re.sub(r"\s+", " ", t)


def score(want: str, got: str, want_year: int | None, got_year: int | None) -> float:
    s = SequenceMatcher(None, norm(want), norm(got)).ratio()
    if norm(want) == norm(got):
        s += 0.15
    if want_year and got_year:
        s += 0.1 if abs(want_year - got_year) <= 1 else -0.35
    return s


def best(items: list[dict], title: str, year: int | None, floor: float = 0.62) -> dict | None:
    scored = sorted(((score(title, i["title"], year, i.get("year")), n, i) for n, i in enumerate(items)),
                    key=lambda t: (-t[0], t[1]))
    return scored[0][2] if scored and scored[0][0] >= floor else None


def _year(text: str | None) -> int | None:
    m = re.match(r"(\d{4})", text or "")
    return int(m.group(1)) if m else None


def _plain(text: str | None) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


class TMDBProvider:
    name = "tmdb"

    def __init__(self, key: str, language: str = "en-US", client: httpx.Client | None = None):
        self.key, self.language = key.strip(), language
        self.http = client or httpx.Client(timeout=15, headers=UA)

    def _get(self, path: str, **params):
        headers = {}
        if self.key.startswith("eyJ"):                 # v4 read-access token
            headers["Authorization"] = f"Bearer {self.key}"
        else:
            params["api_key"] = self.key
        r = self.http.get(f"{TMDB}{path}", params={"language": self.language, **params}, headers=headers)
        r.raise_for_status()
        return r.json()

    def check(self) -> None:
        self._get("/configuration")

    def _poster(self, path: str | None) -> str | None:
        return f"{TMDB_IMG}{path}" if path else None

    def search_movies(self, title: str, year: int | None) -> list[dict]:
        data = self._get("/search/movie", query=title, include_adult="false", **({"year": year} if year else {}))
        return [{"provider": "tmdb", "id": str(r["id"]), "title": r["title"], "year": _year(r.get("release_date")),
                 "overview": r.get("overview") or "", "poster_url": self._poster(r.get("poster_path")),
                 "rating": r.get("vote_average") or None} for r in data.get("results", [])[:8]]

    def movie(self, title: str, year: int | None) -> dict | None:
        hit = best(self.search_movies(title, year), title, year)
        if not hit and year:
            hit = best(self.search_movies(title, None), title, year)
        return self.movie_detail(hit["id"]) if hit else None

    def _cert(self, path: str, pick) -> str | None:
        try:
            return pick(self._get(path))
        except (httpx.HTTPError, KeyError, StopIteration):
            return None

    def movie_detail(self, mid: str) -> dict:
        d = self._get(f"/movie/{mid}")
        cert = self._cert(f"/movie/{mid}/release_dates", lambda j: next(
            (rd["certification"] for res in j["results"] if res["iso_3166_1"] == "US" for rd in res["release_dates"] if rd.get("certification")), None))
        return {"provider": "tmdb", "id": str(d["id"]), "title": d["title"], "year": _year(d.get("release_date")),
                "overview": d.get("overview") or "", "genres": [g["name"] for g in d.get("genres", [])],
                "rating": d.get("vote_average") or None, "runtime": d.get("runtime") or None,
                "poster_url": self._poster(d.get("poster_path")), "cert": cert,
                "ids": {"tmdb": str(d["id"]), **({"imdb": d["imdb_id"]} if d.get("imdb_id") else {})}}

    def search_shows(self, title: str, year: int | None) -> list[dict]:
        data = self._get("/search/tv", query=title, **({"first_air_date_year": year} if year else {}))
        return [{"provider": "tmdb", "id": str(r["id"]), "title": r["name"], "year": _year(r.get("first_air_date")),
                 "overview": r.get("overview") or "", "poster_url": self._poster(r.get("poster_path")),
                 "rating": r.get("vote_average") or None} for r in data.get("results", [])[:8]]

    def show(self, title: str, year: int | None) -> dict | None:
        hit = best(self.search_shows(title, year), title, year)
        if not hit and year:
            hit = best(self.search_shows(title, None), title, year)
        return self.show_detail(hit["id"]) if hit else None

    def show_detail(self, sid: str) -> dict:
        d = self._get(f"/tv/{sid}")
        cert = self._cert(f"/tv/{sid}/content_ratings", lambda j: next(
            (r["rating"] for r in j["results"] if r["iso_3166_1"] == "US" and r.get("rating")), None))
        return {"provider": "tmdb", "id": str(d["id"]), "title": d["name"], "year": _year(d.get("first_air_date")),
                "overview": d.get("overview") or "", "genres": [g["name"] for g in d.get("genres", [])],
                "rating": d.get("vote_average") or None, "poster_url": self._poster(d.get("poster_path")), "cert": cert,
                "ids": {"tmdb": str(d["id"])}}

    def episodes(self, sid: str, season: int) -> dict[tuple[int, int], dict]:
        try:
            d = self._get(f"/tv/{sid}/season/{season}")
        except httpx.HTTPError:
            return {}
        return {(season, e["episode_number"]): {"title": e.get("name") or "", "overview": e.get("overview") or "",
                                                  "still_url": f"{TMDB_IMG}{e['still_path']}" if e.get("still_path") else None}
                for e in d.get("episodes", [])}


class WikipediaProvider:
    """Movies without a key: the film's Wikipedia article gives a summary, the year and the poster."""
    name = "wikipedia"
    API = "https://en.wikipedia.org/w/api.php"

    def __init__(self, client: httpx.Client | None = None):
        self.http = client or httpx.Client(timeout=15, headers=UA)

    def search_movies(self, title: str, year: int | None) -> list[dict]:
        r = polite_get(self.http, self.API, params={
            "action": "query", "format": "json", "generator": "search", "gsrlimit": 8,
            "gsrsearch": f"{title} {year or ''} film".strip(), "prop": "extracts|description",
            "exintro": 1, "explaintext": 1, "exlimit": "max"})
        r.raise_for_status()
        pages = sorted((r.json().get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
        out = []
        for pg in pages:
            desc = pg.get("description") or ""
            if "film" not in desc.lower():
                continue
            m = re.match(r"^(.*?)\s*\((?:\d{4}\s+)?(?:[\w ]+ )?film\)$", pg["title"])
            y = re.search(r"\b((?:18|19|20)\d{2})\b", desc) or re.search(r"\((\d{4}) ", pg["title"])
            out.append({"provider": "wikipedia", "id": str(pg["pageid"]), "page": pg["title"], "title": (m.group(1) if m else pg["title"]),
                        "year": int(y.group(1)) if y else None, "overview": shorten(pg.get("extract") or ""),
                        "genres": [], "poster_url": None})
        return out

    def movie(self, title: str, year: int | None) -> dict | None:
        hit = best(self.search_movies(title, year), title, year, floor=0.7)
        if hit and not hit.get("poster_url"):
            hit = {**hit, "poster_url": self.poster(hit["page"])}
        return hit

    def poster(self, page_title: str) -> str | None:
        """The article's lead image, which for a film is its poster."""
        r = polite_get(self.http, "https://en.wikipedia.org/api/rest_v1/page/summary/" + quote(page_title.replace(" ", "_"), safe=""))
        if r.status_code != 200:
            return None
        d = r.json()
        return (d.get("thumbnail") or d.get("originalimage") or {}).get("source")


def tvmaze_background(tvmaze_id: str, client: httpx.Client | None = None) -> str | None:
    """A show's background picture from TVmaze (used when it has no IMDb id)."""
    r = polite_get(client or httpx.Client(timeout=15, headers=UA), f"{TVMAZE}/shows/{tvmaze_id}/images")
    if r.status_code != 200:
        return None
    for img in r.json():
        if img.get("type") == "background":
            return ((img.get("resolutions") or {}).get("original") or {}).get("url")
    return None


class TVmazeProvider:
    """Shows and episodes without a key."""
    name = "tvmaze"

    def __init__(self, client: httpx.Client | None = None):
        self.http = client or httpx.Client(timeout=15, headers=UA)

    def _shape(self, s: dict) -> dict:
        img = s.get("image") or {}
        return {"provider": "tvmaze", "id": str(s["id"]), "title": s.get("name", ""), "year": _year(s.get("premiered")),
                "overview": _plain(s.get("summary")), "genres": s.get("genres") or [],
                "rating": (s.get("rating") or {}).get("average"), "poster_url": img.get("original") or img.get("medium"),
                "ids": {"tvmaze": str(s["id"]), **({"imdb": s["externals"]["imdb"]} if (s.get("externals") or {}).get("imdb") else {})}}

    def search_shows(self, title: str, year: int | None) -> list[dict]:
        r = polite_get(self.http, f"{TVMAZE}/search/shows", params={"q": title})
        r.raise_for_status()
        return [self._shape(x["show"]) for x in r.json()[:8]]

    def show(self, title: str, year: int | None) -> dict | None:
        return best(self.search_shows(title, year), title, year)

    def show_detail(self, sid: str) -> dict:
        r = polite_get(self.http, f"{TVMAZE}/shows/{sid}")
        r.raise_for_status()
        return self._shape(r.json())

    def episodes(self, sid: str, season: int) -> dict[tuple[int, int], dict]:
        r = polite_get(self.http, f"{TVMAZE}/shows/{sid}/episodes")
        if r.status_code != 200:
            return {}
        return {(e["season"], e["number"]): {"title": e.get("name") or "", "overview": _plain(e.get("summary")),
                                             "still_url": (e.get("image") or {}).get("original")}
                for e in r.json() if e.get("number") is not None}


def background_url(ids: dict | None) -> str | None:
    """A wide background picture for a title, from its IMDb id (keyless; IMDb-sourced)."""
    imdb = (ids or {}).get("imdb") or ""
    return f"https://images.metahub.space/background/medium/{imdb}/img" if re.fullmatch(r"tt\d{6,10}", imdb) else None


class CinemetaProvider:
    """Movies and shows without a key. IMDb-sourced posters, summaries, ratings and per-episode stills."""
    name = "cinemeta"

    def __init__(self, client: httpx.Client | None = None):
        self.http = client or httpx.Client(timeout=15, headers=UA)

    def _shape(self, m: dict) -> dict:
        rt = re.search(r"\d+", str(m.get("runtime") or ""))
        try:
            rating = float(m.get("imdbRating")) if m.get("imdbRating") else None
        except ValueError:
            rating = None
        iid = m.get("imdb_id") or m.get("id") or ""
        return {"provider": "cinemeta", "id": iid, "title": m.get("name", ""), "year": _year(str(m.get("year") or m.get("releaseInfo") or "")),
                "overview": shorten(m.get("description") or m.get("overview") or ""), "genres": m.get("genres") or [],
                "rating": rating, "runtime": int(rt.group()) if rt else None,
                "poster_url": (m.get("poster") or "").replace("/poster/small/", "/poster/medium/") or None,
                "ids": {"imdb": iid} if iid.startswith("tt") else {}}

    def _search(self, kind: str, title: str) -> list[dict]:
        r = polite_get(self.http, f"{CINEMETA}/catalog/{kind}/top/search={quote(title, safe='')}.json")
        if r.status_code != 200:
            return []
        return [self._shape(m) for m in r.json().get("metas", [])[:8]]

    def _detail(self, kind: str, iid: str) -> dict:
        r = polite_get(self.http, f"{CINEMETA}/meta/{kind}/{iid}.json")
        r.raise_for_status()
        return self._shape(r.json().get("meta") or {})

    def search_movies(self, title: str, year: int | None) -> list[dict]:
        return self._search("movie", title)

    def movie(self, title: str, year: int | None) -> dict | None:
        hit = best(self.search_movies(title, year), title, year)
        return {**hit, **{k: v for k, v in self._detail("movie", hit["id"]).items() if v}} if hit else None

    def movie_detail(self, mid: str) -> dict:
        return self._detail("movie", mid)

    def search_shows(self, title: str, year: int | None) -> list[dict]:
        return self._search("series", title)

    def show(self, title: str, year: int | None) -> dict | None:
        hit = best(self.search_shows(title, year), title, year)
        return {**hit, **{k: v for k, v in self._detail("series", hit["id"]).items() if v}} if hit else None

    def show_detail(self, sid: str) -> dict:
        return self._detail("series", sid)

    def episodes(self, sid: str, season: int) -> dict[tuple[int, int], dict]:
        r = polite_get(self.http, f"{CINEMETA}/meta/series/{sid}.json")
        if r.status_code != 200:
            return {}
        return {(v["season"], v["episode"]): {"title": v.get("name") or v.get("title") or "", "overview": v.get("overview") or v.get("description") or "",
                                              "still_url": v.get("thumbnail")}
                for v in (r.json().get("meta") or {}).get("videos", []) if v.get("season") == season and v.get("episode") is not None}


class Chain:
    """Several providers behind one interface: the first with an answer wins, later ones fill in a missing poster."""

    def __init__(self, *providers):
        self.providers = providers
        self.name = providers[0].name

    def _owner(self, pid: str):
        return next((p for p in self.providers if (p.name == "cinemeta") == str(pid).startswith("tt")), self.providers[0])

    def _find(self, method: str, title: str, year: int | None) -> dict | None:
        hit = None
        for p in self.providers:
            try:
                got = getattr(p, method)(title, year)
            except Exception:  # noqa: BLE001 - one source being down must not stop the others
                continue
            if got and not hit:
                hit = got
            if hit and hit.get("poster_url"):
                break
            if got and hit is not got and got.get("poster_url"):
                hit = {**hit, "poster_url": got["poster_url"]}
                break
        return hit

    def movie(self, title, year): return self._find("movie", title, year)
    def show(self, title, year): return self._find("show", title, year)

    def search_movies(self, title, year):
        out = []
        for p in self.providers:
            try:
                out += p.search_movies(title, year)
            except Exception:  # noqa: BLE001
                pass
        return out

    def search_shows(self, title, year):
        out = []
        for p in self.providers:
            try:
                out += p.search_shows(title, year)
            except Exception:  # noqa: BLE001
                pass
        return out

    def movie_detail(self, mid):
        return self._owner(mid).movie_detail(mid) if hasattr(self._owner(mid), "movie_detail") else {}

    def show_detail(self, sid): return self._owner(sid).show_detail(sid)
    def episodes(self, sid, season): return self._owner(sid).episodes(sid, season)


def pick_providers(setting: dict):
    """(movie provider, show provider) for the saved settings; (None, None) when switched off."""
    mode = (setting or {}).get("provider", "auto")
    key = (setting or {}).get("tmdb_key", "").strip()
    if mode == "none":
        return None, None
    if key and mode in ("auto", "tmdb"):
        t = TMDBProvider(key, (setting or {}).get("language", "en-US"))
        return t, t
    return Chain(CinemetaProvider(), WikipediaProvider()), Chain(TVmazeProvider(), CinemetaProvider())
