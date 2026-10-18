"""Fills in the details of every library title: name, year, summary, genres and artwork."""
from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path

import httpx

from .. import media
from . import art
from .parse import local_poster, nfo_for, parse_name, show_nfo_for
from .providers import norm, pick_providers

log = logging.getLogger("hush.library")
RETRY_UNMATCHED_AFTER = 7 * 86400
DEFAULTS = {"provider": "auto", "tmdb_key": "", "language": "en-US"}


def show_key_for(title: str) -> str:
    return hashlib.sha1(f"show:{norm(title)}".encode()).hexdigest()[:16]


class MetadataService:
    def __init__(self, cfg, db, registry):
        self.cfg, self.db, self.registry = cfg, db, registry
        self.art_dir = cfg.data_dir / "art"

    # ---- settings -------------------------------------------------------------
    def settings(self) -> dict:
        return {**DEFAULTS, **self.db.get_setting("metadata", {})}

    def public_settings(self) -> dict:
        s = self.settings()
        return {"provider": s["provider"], "language": s["language"], "has_key": bool(s["tmdb_key"])}

    def update_settings(self, patch: dict) -> dict:
        s = self.settings()
        if patch.get("provider") in ("auto", "tmdb", "none"):
            s["provider"] = patch["provider"]
        if "tmdb_key" in patch:
            s["tmdb_key"] = str(patch["tmdb_key"]).strip()
        if "language" in patch and str(patch["language"]).strip():
            s["language"] = str(patch["language"]).strip()[:10]
        if s["provider"] == "tmdb" and not s["tmdb_key"]:
            raise ValueError("Add your TMDB key first, or choose Automatic")
        self.db.set_setting("metadata", s)
        return self.public_settings()

    def test(self) -> str:
        movies, shows = pick_providers(self.settings())
        if movies is None:
            return "Online details are switched off"
        if movies.name == "tmdb":
            movies.check()
            return "TMDB accepted the key"
        movies.search_movies("Heat", 1995)
        shows.search_shows("Friends", None)
        return "The free sources (Wikipedia and TVmaze) answered"

    # ---- one title -----------------------------------------------------------------
    def _fetch_art(self, key: str, local: Path | None, url: str | None, video_args, duration) -> bool:
        dst = art.art_path(self.art_dir, key)
        if local and art.from_file(self.cfg.ffmpeg, local, dst):
            return True
        if url and art.from_url(self.cfg.ffmpeg, url, dst):
            return True
        return bool(video_args) and art.from_video(self.cfg.ffmpeg, video_args, duration, dst)

    def enrich(self, row: dict, providers=None, cache: dict | None = None) -> dict:
        """Work out and save the details for one library_items row."""
        movies, shows = providers if providers is not None else pick_providers(self.settings())
        cache = cache if cache is not None else {}
        sid, iid, key = row["source_id"], row["item_id"], row["media_key"]
        old = self.db.get_meta(key)
        if old and old.get("locked"):
            return old
        ref = self.registry.get(sid).resolve(iid)
        path = Path(ref.path) if ref.path else None
        parsed = parse_name(ref.name or row.get("title") or "")
        if path and parsed["kind"] == "movie" and not parsed["year"]:
            folder = parse_name(path.parent.name)
            if folder["year"] and folder["kind"] == "movie":
                parsed["year"] = folder["year"]
                parsed["title"] = parsed["title"] if len(parsed["title"]) > 3 else folder["title"]
        nfo = nfo_for(path) if path else {}
        m = {"media_key": key, "source_id": sid, "item_id": iid, "kind": parsed["kind"], "title": parsed["title"],
             "year": parsed["year"], "season": parsed["season"], "episode": parsed["episode"],
             "overview": "", "genres": [], "rating": None, "runtime": None, "ids": {}, "provider": "name", "art": 0}
        poster_url = None
        try:
            if parsed["kind"] == "movie":
                self._enrich_movie(m, nfo, movies, parsed)
                poster_url = m.pop("_poster_url", None)
            else:
                poster_url = self._enrich_episode(m, nfo, path, shows, parsed, cache)
        except httpx.HTTPError as exc:
            log.warning("details lookup failed for %s: %s", ref.name, exc)
        video_args = None
        duration = None
        if not art.art_path(self.art_dir, key).exists() or not (old and old.get("art")):
            local = local_poster(path) if (path and parsed["kind"] == "movie") else None
            try:
                if not local and not poster_url:
                    video_args = media.ffmpeg_input(ref, sid, iid)
                    duration = media.probe(self.cfg.ffprobe, ref, sid, iid, timeout=45).duration
            except Exception as exc:  # noqa: BLE001
                log.info("no thumbnail source for %s: %s", ref.name, exc)
            m["art"] = self._fetch_art(key, local, poster_url, video_args, duration)
        else:
            m["art"] = 1
        self.db.save_meta(m)
        return m

    def _enrich_movie(self, m: dict, nfo: dict, movies, parsed: dict) -> None:
        if nfo.get("title"):
            m.update({k: nfo[k] for k in ("title", "year", "overview", "genres", "runtime", "rating", "ids") if k in nfo})
            m["provider"] = "nfo"
        if movies and (not m["overview"] or m["provider"] != "nfo"):
            hit = movies.movie(m["title"], m["year"])
            if hit:
                if m["provider"] != "nfo":
                    m["title"], m["year"] = hit["title"], hit.get("year") or m["year"]
                    m["provider"] = hit["provider"]
                for k in ("overview", "genres", "runtime", "rating"):
                    if not m.get(k) and hit.get(k):
                        m[k] = hit[k]
                m["ids"] = {**hit.get("ids", {}), **m["ids"]}
                m["_poster_url"] = hit.get("poster_url")
            time.sleep(0.6)

    def _enrich_episode(self, m: dict, nfo: dict, path: Path | None, shows, parsed: dict, cache: dict) -> str | None:
        show_title, show_year = parsed["title"], parsed["year"]
        snfo = show_nfo_for(path) if path else {}
        if snfo.get("title"):
            show_title, show_year = snfo["title"], snfo.get("year") or show_year
        elif nfo.get("show"):
            show_title = nfo["show"]
        key = show_key_for(show_title)
        m["show_key"] = key
        m["title"] = nfo.get("title") or parsed["ep_title"]
        for k in ("season", "episode"):
            if nfo.get(k) is not None:
                m[k] = nfo[k]
        if nfo.get("overview"):
            m["overview"], m["provider"] = nfo["overview"], "nfo"
        for k in ("runtime", "rating"):
            if nfo.get(k):
                m[k] = nfo[k]
        show = self.db.get_show(key)
        if show is None:
            show = {"show_key": key, "title": show_title, "year": show_year, "overview": snfo.get("overview", ""),
                    "genres": snfo.get("genres", []), "rating": snfo.get("rating"), "ids": snfo.get("ids", {}),
                    "provider": "nfo" if snfo.get("title") else "name", "art": 0}
            self.db.save_show(show)
        found = None
        if shows and not show.get("locked"):
            if key not in cache:
                cache[key] = None
                if show["provider"] in ("name", "nfo") and not (show.get("overview") and show["art"]):
                    hit = shows.show(show_title, show_year)
                    time.sleep(0.6)
                    if hit:
                        cache[key] = hit
                        self._apply_show(show, hit, snfo)
                elif show.get("ids"):
                    cache[key] = {"id": show["ids"].get(shows.name) or show["ids"].get("tmdb") or show["ids"].get("tvmaze")}
            found = cache.get(key)
        if found and found.get("id") and not m["overview"] and m.get("season") is not None:
            ck = ("eps", key, m["season"])
            if ck not in cache:
                cache[ck] = shows.episodes(found["id"], m["season"])
                time.sleep(0.6)
            ep = cache[ck].get((m["season"], m["episode"]))
            if ep:
                m["title"] = m["title"] or ep["title"]
                m["overview"], m["provider"] = ep["overview"], shows.name
                return ep.get("still_url")
        return None

    def _apply_show(self, show: dict, hit: dict, snfo: dict) -> None:
        if show["provider"] != "nfo":
            show["title"], show["year"] = hit["title"], hit.get("year") or show["year"]
        show["provider"] = hit["provider"] if show["provider"] != "nfo" else "nfo"
        for k in ("overview", "genres", "rating"):
            if not show.get(k) and hit.get(k):
                show[k] = hit[k]
        show["ids"] = {**hit.get("ids", {}), **show.get("ids", {})}
        if not art.art_path(self.art_dir, show["show_key"]).exists():
            show["art"] = bool(hit.get("poster_url") and art.from_url(
                self.cfg.ffmpeg, hit["poster_url"], art.art_path(self.art_dir, show["show_key"])))
        self.db.save_show(show)

    # ---- the whole library ---------------------------------------------------------------
    def finish_shows(self) -> None:
        """Shows without a poster of their own borrow their first episode's thumbnail."""
        for s in self.db.list_shows():
            dst = art.art_path(self.art_dir, s["show_key"])
            if s["art"] and dst.exists():
                continue
            for ep in self.db.episodes_of(s["show_key"]):
                src = art.art_path(self.art_dir, ep["media_key"])
                if ep["art"] and src.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    dst.write_bytes(src.read_bytes())
                    full = self.db.get_show(s["show_key"])
                    full["art"] = 1
                    self.db.save_show(full)
                    break

    def process_library(self, retry_unmatched: bool = True) -> dict:
        rows = self.db.library_without_meta()
        if retry_unmatched:
            cutoff = time.time() - RETRY_UNMATCHED_AFTER
            for r in self.db._all("SELECT l.* FROM library_items l JOIN meta m ON m.media_key=l.media_key "
                                  "WHERE m.provider='name' AND m.locked=0 AND m.updated_at<?", (cutoff,)):
                rows.append(r)
        providers, cache = pick_providers(self.settings()), {}
        done = failed = 0
        for r in rows:
            try:
                self.enrich(r, providers, cache)
                done += 1
            except Exception as exc:  # noqa: BLE001
                failed += 1
                log.warning("details failed for %s: %s", r.get("title"), exc)
        self.finish_shows()
        return {"processed": done, "failed": failed}

    # ---- fixing a wrong match by hand ---------------------------------------------------------
    def candidates(self, kind: str, query: str, year: int | None) -> list[dict]:
        movies, shows = pick_providers(self.settings())
        prov = movies if kind == "movie" else shows
        if prov is None:
            return []
        return (prov.search_movies if kind == "movie" else prov.search_shows)(query, year)[:8]

    def apply_choice(self, media_key: str, cand: dict) -> dict:
        """Use this search result for a title; the choice is locked against later refreshes."""
        m = self.db.get_meta(media_key)
        if not m:
            raise KeyError(media_key)
        movies, shows = pick_providers(self.settings())
        if m["kind"] == "movie":
            if movies is None:
                raise ValueError("Online details are switched off")
            hit = movies.movie_detail(cand["id"]) if hasattr(movies, "movie_detail") else cand
            if not hit or not hit.get("title"):
                raise ValueError("That entry could not be found")
            m.update({k: hit[k] for k in ("title", "year", "overview", "genres", "runtime", "rating", "ids") if hit.get(k)})
            m["provider"], m["locked"] = hit["provider"], 1
            if hit.get("poster_url"):
                m["art"] = art.from_url(self.cfg.ffmpeg, hit["poster_url"], art.art_path(self.art_dir, media_key)) or m["art"]
        else:
            if shows is None:
                raise ValueError("Online details are switched off")
            hit = shows.show_detail(cand["id"])
            show = self.db.get_show(m["show_key"]) or {"show_key": m["show_key"], "art": 0}
            show.update({"title": hit["title"], "year": hit.get("year"), "overview": hit["overview"],
                         "genres": hit.get("genres", []), "rating": hit.get("rating"), "ids": hit.get("ids", {}),
                         "provider": hit["provider"], "locked": 1})
            if hit.get("poster_url") and art.from_url(self.cfg.ffmpeg, hit["poster_url"], art.art_path(self.art_dir, m["show_key"])):
                show["art"] = 1
            self.db.save_show(show)
        self.db.save_meta(m)
        return m
