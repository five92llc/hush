"""Hush HTTP API + web UI."""
from __future__ import annotations

import json
import logging
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from . import discover, media, stream
from .hls import HLSError, HLSManager
from .live import LiveTV
from .analysis.jobs import Analyzer
from .auth import COOKIE, SESSION_TTL, Auth
from .config import Config, load_config
from .db import DB
from .sources import Registry, SourceError, discover_dlna, media_key
from .library import transcript as tr
from .library.rename import RenameError, Renamer
from .library.service import MetadataService
from .notify import Notifier
from .tasks import TaskManager
from .sources.base import enc

log = logging.getLogger("hush")
WEB = Path(__file__).parent / "web"
CACHE_TTL = 600


class Cache:
    """Tiny TTL cache for resolved refs and probe results."""

    def __init__(self):
        self._d: dict[Any, tuple[float, Any]] = {}

    def get(self, key):
        hit = self._d.get(key)
        if hit and time.time() - hit[0] < CACHE_TTL:
            return hit[1]
        return None

    def put(self, key, value):
        if len(self._d) > 500:
            self._d.clear()
        self._d[key] = (time.time(), value)
        return value


def create_app(cfg: Config | None = None) -> FastAPI:
    cfg = cfg or load_config()
    db = DB(cfg.db_path)
    auth = Auth(cfg.password, cfg.secret_key, db.get_setting("password_hash"))
    registry = Registry(cfg.sources, db)
    media.configure(f"http://127.0.0.1:{cfg.port}", auth.internal_token)
    analyzer = Analyzer(cfg, db, registry)
    library = MetadataService(cfg, db, registry)
    hls = HLSManager(cfg.data_dir / "hls")
    livetv = LiveTV(cfg, db, registry)
    renamer = Renamer(db, registry)
    renamer.cache_dir, renamer.art_dir = cfg.cache_dir, library.art_dir
    tasks = TaskManager(cfg, db, registry, analyzer, library, livetv)
    notifier = Notifier(db)
    analyzer.on_event = notifier.event
    cache = Cache()

    # Restore the ad-hoc URL list.
    registry.get("url").urls = db.get_setting("recent_urls", [])

    app = FastAPI(title="Hush", docs_url=None, redoc_url=None)
    app.state.cfg, app.state.db, app.state.analyzer, app.state.tasks, app.state.hls = cfg, db, analyzer, tasks, hls

    @app.on_event("startup")
    def _start():
        analyzer.start()
        tasks.start()
        if not auth.enabled:
            log.warning("No password set: anyone on your network can use Hush. "
                        "Set `password:` in config.yaml or HUSH_PASSWORD.")

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        if resp.headers.get("content-type", "").startswith("text/html"):
            resp.headers.setdefault("Content-Security-Policy",
                                    "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; "
                                    "style-src 'self' 'unsafe-inline'; frame-ancestors 'none'")
        return resp

    @app.exception_handler(SourceError)
    async def _source_error(_, exc: SourceError):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    need = Depends(auth.require)

    # ---- helpers --------------------------------------------------------
    def resolve(source_id: str, item_id: str):
        key = ("ref", source_id, item_id)
        return cache.get(key) or cache.put(key, registry.get(source_id).resolve(item_id))

    def probe(source_id: str, item_id: str):
        key = ("probe", source_id, item_id)
        hit = cache.get(key)
        if hit:
            return hit
        ref = resolve(source_id, item_id)
        try:
            result = cache.put(key, media.probe(cfg.ffprobe, ref, source_id, item_id))
            if result.duration is None and ref.url and not ref.live:
                ref.live = True          # a stream with no length (IPTV channel): no seeking, scanning or filtering
            return result
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, f"Could not read media: {exc}")

    # ---- pages & session ------------------------------------------------
    app.mount("/static", StaticFiles(directory=WEB), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/api/session")
    def session(request: Request):
        return {"auth_required": auth.enabled,
                "logged_in": (not auth.enabled) or auth.valid_session(request.cookies.get(COOKIE))}

    @app.post("/api/login")
    def login(request: Request, body: dict = Body(...)):
        if not auth.enabled:
            return {"ok": True}
        if not auth.check_password(str(body.get("password", "")), request.client.host if request.client else "?"):
            raise HTTPException(401, "Wrong password")
        resp = JSONResponse({"ok": True})
        resp.set_cookie(COOKIE, auth.make_session(), max_age=SESSION_TTL, httponly=True,
                        samesite="strict", secure=request.url.scheme == "https")
        return resp

    @app.post("/api/password", dependencies=[need])
    def change_password(request: Request, body: dict = Body(...)):
        new = str(body.get("new", ""))
        if not new:   # an empty password would switch the login off
            raise HTTPException(400, "Enter a new password")
        if auth.enabled and not auth.check_password(str(body.get("current", "")),
                                                    request.client.host if request.client else "?"):
            raise HTTPException(403, "Current password is wrong")
        db.set_setting("password_hash", auth.set_password(new))
        resp = JSONResponse({"ok": True})   # other signed-in browsers are signed out
        resp.set_cookie(COOKIE, auth.make_session(), max_age=SESSION_TTL, httponly=True,
                        samesite="strict", secure=request.url.scheme == "https")
        return resp

    @app.post("/api/logout")
    def logout():
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(COOKIE)
        return resp

    @app.get("/api/config", dependencies=[need])
    def config_info():
        return {"engines": analyzer.engines(), "categories": analyzer.wordlist.categories_info(),
                "source_types": ["local", "smb", "ftp", "sftp", "http", "dlna", "jellyfin", "plex"]}

    # ---- sources --------------------------------------------------------
    @app.get("/api/sources", dependencies=[need])
    def list_sources():
        return registry.list()

    @app.post("/api/sources", dependencies=[need])
    def add_source(body: dict = Body(...)):
        return registry.add_runtime(body)

    @app.delete("/api/sources/{source_id}", dependencies=[need])
    def remove_source(source_id: str):
        registry.remove_runtime(source_id)
        return {"ok": True}

    @app.get("/api/network/scan", dependencies=[need])
    def network_scan():
        return discover.scan()

    @app.get("/api/dlna/discover", dependencies=[need])
    def dlna_discover():
        return discover_dlna()

    @app.get("/api/browse/{source_id}", dependencies=[need])
    def browse(source_id: str, dir: str = ""):
        entries = [e.to_dict(source_id) for e in registry.get(source_id).browse(dir)]
        keys = [e["media_key"] for e in entries if "media_key" in e]
        done = db.filtered_keys(keys)
        prog = db.progress_map(keys)
        for e in entries:
            if "media_key" in e:
                e["filtered"] = e["media_key"] in done
                pr = prog.get(e["media_key"])
                if pr:
                    e["watched"] = bool(pr["finished"])
                    e["resume"] = pr["position"] if not pr["finished"] else 0
        return entries

    @app.post("/api/open-url", dependencies=[need])
    def open_url(body: dict = Body(...)):
        url = str(body.get("url", "")).strip()
        src = registry.get("url")
        src.validate(url)
        recent = [u for u in src.urls if u["url"] != url]
        recent.insert(0, {"name": body.get("name") or src.display_name(url), "url": url})
        src.urls = recent[:30]
        db.set_setting("recent_urls", src.urls)
        return {"source_id": "url", "item_id": enc(url), "kind": src.kind_of(url)}

    # ---- media ----------------------------------------------------------
    @app.get("/api/media/{source_id}/{item_id}", dependencies=[need])
    def media_info(source_id: str, item_id: str, audio: int | None = None):
        ref = resolve(source_id, item_id)
        p = probe(source_id, item_id)
        key = media_key(source_id, item_id)
        f = db.get_filter(key)
        prog = db.get_progress(key)
        resume = ({"position": prog["position"], "finished": bool(prog["finished"])}
                  if prog and not ref.live else None)
        return {"title": ref.title, "kind": "video" if p.video else "audio", "name": ref.name,
                "live": ref.live, "resume": resume, "media_key": key, "probe": p.to_dict(), "mode": media.choose_mode(ref, p, audio),
                "has_filter": bool(f), "job": db.active_job_for(key)}

    @app.get("/api/raw/{source_id}/{item_id}", dependencies=[need])
    async def raw(request: Request, source_id: str, item_id: str):
        ref = await run_in_threadpool(resolve, source_id, item_id)
        return await stream.serve_raw(request, ref)

    @app.get("/internal/raw/{source_id}/{item_id}", include_in_schema=False)
    async def internal_raw(request: Request, source_id: str, item_id: str, k: str = ""):
        host = request.client.host if request.client else ""
        if host not in ("127.0.0.1", "::1") or k != auth.internal_token:
            raise HTTPException(403)
        ref = await run_in_threadpool(resolve, source_id, item_id)
        return await stream.serve_raw(request, ref)

    @app.get("/api/stream/{source_id}/{item_id}", dependencies=[need])
    async def live(request: Request, source_id: str, item_id: str,
                   start: float = 0.0, audio: int | None = None, mode: str | None = None):
        ref = await run_in_threadpool(resolve, source_id, item_id)
        p = await run_in_threadpool(probe, source_id, item_id)
        mode = mode if mode in ("remux", "transcode", "audio") else media.choose_mode(ref, p, audio)
        if mode == "direct":
            mode = "audio" if not p.video else "remux"
        cmd, mime = stream.build_ffmpeg_cmd(cfg, ref, source_id, item_id, mode, max(0.0, start), audio)
        return await stream.ffmpeg_response(request, cmd, mime)

    @app.get("/api/hls/start/{source_id}/{item_id}", dependencies=[need])
    def hls_start(source_id: str, item_id: str, start: float = 0.0, audio: int | None = None,
                  mode: str | None = None, cats: str = "", filter: int = 1, tab: str = ""):
        """Begin an HLS session (for Safari and iOS) and send the browser to its playlist.
        Safari cannot route HLS audio through the Web Audio API, so the filter's muting is done here."""
        ref = resolve(source_id, item_id)
        p = probe(source_id, item_id)
        mode = mode if mode in ("remux", "transcode", "audio") else media.choose_mode(ref, p, audio)
        if mode == "direct":
            mode = "audio" if not p.video else "remux"
        f = db.get_filter(media_key(source_id, item_id))
        ranges = _select(f["ranges"], cats) if (f and filter and not ref.live) else None
        try:
            sid = hls.create(lambda d: stream.build_ffmpeg_cmd(
                cfg, ref, source_id, item_id, mode, 0.0 if ref.live else max(0.0, start), audio,
                mute_ranges=ranges, container="hls", hls_dir=d)[0], owner=tab[:40])
        except HLSError as exc:
            raise HTTPException(502, str(exc))
        return RedirectResponse(f"/api/hls/{sid}/index.m3u8", status_code=307)

    @app.get("/api/hls/{sid}/{name}", dependencies=[need])
    def hls_file(sid: str, name: str):
        f = hls.file(sid, name)
        if not f:
            raise HTTPException(404)
        if name.endswith(".m3u8"):
            return FileResponse(f, media_type="application/vnd.apple.mpegurl", headers={"Cache-Control": "no-store"})
        return FileResponse(f, media_type="video/mp2t", headers={"Cache-Control": "private, max-age=300"})

    @app.get("/api/seekpoint/{source_id}/{item_id}", dependencies=[need])
    def seekpoint(source_id: str, item_id: str, t: float, mode: str = "remux"):
        """Where a live stream requested at ``t`` will actually start."""
        if mode != "remux" or t <= 0:
            return {"start": max(0.0, t)}
        ref = resolve(source_id, item_id)
        return {"start": round(media.keyframe_before(cfg.ffprobe, ref, source_id, item_id, t), 3)}

    @app.get("/api/subtitle/{source_id}/{item_id}/{track}", dependencies=[need])
    def subtitle(source_id: str, item_id: str, track: str, format: str = "vtt", download: bool = False):
        if format not in ("vtt", "srt"):
            raise HTTPException(400, "format must be vtt or srt")
        ref = resolve(source_id, item_id)
        if track.startswith("side"):
            n = int(track[4:])
            if n >= len(ref.subtitle_paths):
                raise HTTPException(404)
            args = ["-i", ref.subtitle_paths[n]]
            mapping = ["-map", "0:s:0"]
        else:
            args = media.ffmpeg_input(ref, source_id, item_id)
            mapping = ["-map", f"0:{int(track)}"]
        cmd = [cfg.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", *args, *mapping,
               "-f", "webvtt" if format == "vtt" else "srt", "pipe:1"]
        try:
            out = subprocess.run(cmd, capture_output=True, timeout=900, check=True).stdout
        except subprocess.SubprocessError as exc:
            raise HTTPException(502, f"subtitle extraction failed: {exc}")
        headers = {"Cache-Control": "private, max-age=3600"}
        if download:
            headers["Content-Disposition"] = f'attachment; filename="{ref.title} captions.{format}"'
        return Response(out, media_type=("text/vtt" if format == "vtt" else "application/x-subrip") + "; charset=utf-8",
                        headers=headers)

    @app.get("/api/sidecars/{source_id}/{item_id}", dependencies=[need])
    def sidecars(source_id: str, item_id: str):
        ref = resolve(source_id, item_id)
        return [{"id": f"side{i}", "label": Path(p).name} for i, p in enumerate(ref.subtitle_paths)]

    # ---- external players (VLC, Kodi, TVs) --------------------------------
    def _filtered_path(source_id: str, item_id: str) -> str:
        return f"/api/filtered/{source_id}/{item_id}.mkv"

    @app.get("/api/external/{source_id}/{item_id}", dependencies=[need])
    def external(request: Request, source_id: str, item_id: str, cats: str = ""):
        path = _filtered_path(source_id, item_id)
        base = cfg.public_url.rstrip("/") or str(request.base_url).rstrip("/")
        q = f"sig={auth.sign_path(path)}" + (f"&cats={cats}" if cats else "")
        return {"url": f"{base}{path}?{q}", "expires_in_hours": 12}

    @app.get("/api/filtered/{source_id}/{item_id}.mkv", dependencies=[need])
    async def filtered(request: Request, source_id: str, item_id: str, cats: str = "", start: float = 0.0):
        ref = await run_in_threadpool(resolve, source_id, item_id)
        p = await run_in_threadpool(probe, source_id, item_id)
        f = db.get_filter(media_key(source_id, item_id))
        ranges = _select(f["ranges"] if f else [], cats)
        mode = "audio" if not p.video else "remux"   # video is copied untouched
        if start > 0 and mode == "remux":
            start = await run_in_threadpool(media.keyframe_before, cfg.ffprobe, ref, source_id, item_id, start)
        cmd, mime = stream.build_ffmpeg_cmd(cfg, ref, source_id, item_id, mode, start,
                                            mute_ranges=ranges, container="matroska")
        return await stream.ffmpeg_response(request, cmd, mime)

    def _select(ranges: list[dict], cats: str) -> list[dict]:
        wanted = set(cats.split(",")) if cats else None
        return [r for r in ranges if r.get("enabled", True)
                and (wanted is None or r.get("category") in wanted or r.get("source") == "manual")]

    # ---- filters --------------------------------------------------------
    @app.get("/api/filters/{key}", dependencies=[need])
    def get_filter(key: str):
        f = db.get_filter(key)
        if not f:
            raise HTTPException(404, "No filter yet")
        return f

    @app.put("/api/filters/{key}", dependencies=[need])
    def put_filter(key: str, body: dict = Body(...)):
        existing = db.get_filter(key)
        source_id = body.get("source_id") or (existing or {}).get("source_id")
        item_id = body.get("item_id") or (existing or {}).get("item_id")
        if not source_id or not item_id or media_key(source_id, item_id) != key:
            raise HTTPException(400, "source_id/item_id do not match this media")
        ranges = []
        for r in body.get("ranges", []):
            s, e = float(r["start"]), float(r["end"])
            if e <= s or s < 0:
                continue
            ranges.append({"id": str(r.get("id") or uuid.uuid4().hex[:10]), "start": round(s, 3),
                           "end": round(e, 3), "words": [str(w) for w in r.get("words", [])][:20],
                           "category": str(r.get("category") or "manual"),
                           "context": str(r.get("context", ""))[:500],
                           "source": "manual" if r.get("source") == "manual" else "auto",
                           "enabled": bool(r.get("enabled", True))})
        ranges.sort(key=lambda r: r["start"])
        db.save_filter(key, source_id, item_id, body.get("title") or (existing or {}).get("title", ""),
                       (existing or {}).get("duration") or body.get("duration"),
                       (existing or {}).get("engine", "manual"), ranges)
        return db.get_filter(key)

    @app.delete("/api/filters/{key}", dependencies=[need])
    def delete_filter(key: str):
        db.delete_filter(key)
        return {"ok": True}

    @app.post("/api/filters/{key}/rematch", dependencies=[need])
    def rematch(key: str):
        f = analyzer.rematch(key)
        if not f:
            raise HTTPException(404, "No cached transcript; run analysis again")
        return f

    @app.get("/api/filters/{key}/export", dependencies=[need])
    def export_filter(key: str, format: str = Query("json", pattern="^(json|edl)$"), cats: str = ""):
        f = db.get_filter(key)
        if not f:
            raise HTTPException(404)
        stem = "".join(c for c in (f.get("title") or key) if c.isalnum() or c in " -_.").strip() or key
        if format == "edl":
            # Kodi EDL: "<start> <end> 1" = mute. Save next to the video as <name>.edl
            lines = [f"{r['start']:.3f}\t{r['end']:.3f}\t1" for r in _select(f["ranges"], cats)]
            return PlainTextResponse("\n".join(lines) + "\n", headers={
                "Content-Disposition": f'attachment; filename="{stem}.edl"'})
        payload = {"hush_filter": 1, "title": f["title"], "duration": f["duration"],
                   "engine": f["engine"], "ranges": f["ranges"]}
        return Response(json.dumps(payload, indent=1), media_type="application/json", headers={
            "Content-Disposition": f'attachment; filename="{stem}.hush.json"'})

    # ---- analysis jobs ----------------------------------------------------
    @app.post("/api/analyze", dependencies=[need])
    def analyze(body: dict = Body(...)):
        source_id, item_id = body["source_id"], body["item_id"]
        ref = resolve(source_id, item_id)
        try:
            probe(source_id, item_id)          # a stream with no length is marked live by the probe
        except HTTPException:
            pass
        if ref.live:
            raise HTTPException(400, "Live streams can't be scanned: they have no fixed length. Play them unfiltered.")
        engine = body.get("engine")
        if engine not in (None, "auto", "whisper", "subtitles"):
            raise HTTPException(400, "bad engine")
        title = body.get("title") or ""
        return analyzer.submit(source_id, item_id, title, None if engine in (None, "auto") else engine)

    @app.post("/api/jobs/{job_id}/next", dependencies=[need])
    def jobs_next(job_id: str):
        job = analyzer.scan_next(job_id)
        if not job:
            raise HTTPException(404)
        return job

    # ---- notifications ------------------------------------------------------
    @app.get("/api/notifications", dependencies=[need])
    def notifications_get():
        return notifier.config()

    @app.put("/api/notifications", dependencies=[need])
    def notifications_put(body: dict = Body(...)):
        return notifier.update(body)

    @app.post("/api/notifications/test", dependencies=[need])
    def notifications_test():
        notifier.test()
        return {"ok": True}

    @app.post("/api/scan-folder", dependencies=[need])
    def scan_folder(body: dict = Body(...)):
        """Queue every unscanned title under a folder (the library's "Scan all")."""
        return analyzer.scan_tree(body["source_id"], body.get("dir_id") or "",
                                  retry_failed=bool(body.get("retry_failed", True)))

    # ---- library: titles, shows, artwork -------------------------------------
    def _card(m: dict) -> dict:
        m = dict(m)
        m["art_url"] = f"/api/art/{m['media_key']}.jpg" if m.get("art") else None
        m["scanned"] = bool(m.get("scanned"))
        m["watched"] = bool(m.get("watched"))
        return m

    @app.get("/api/library/movies", dependencies=[need])
    def library_movies():
        return [_card(m) for m in db.list_movies()]

    @app.get("/api/library/shows", dependencies=[need])
    def library_shows():
        out = []
        for s in db.list_shows():
            s["art_url"] = f"/api/art/{s['show_key']}.jpg" if s.get("art") else None
            s["scanned"] = int(s.get("scanned") or 0)
            s["watched"] = int(s.get("watched") or 0)
            out.append(s)
        return out

    @app.get("/api/library/shows/{show_key}", dependencies=[need])
    def library_show(show_key: str):
        show = db.get_show(show_key)
        if not show:
            raise HTTPException(404)
        show["art_url"] = f"/api/art/{show_key}.jpg" if show.get("art") else None
        return {"show": show, "episodes": [_card(e) for e in db.episodes_of(show_key)]}

    @app.get("/api/library/title/{key}", dependencies=[need])
    def library_title(key: str):
        m = db.get_meta(key)
        if not m:
            raise HTTPException(404)
        m["scanned"] = bool(db.get_filter(key))
        pr = db.get_progress(key) or {}
        m["position"], m["duration"], m["watched"] = pr.get("position"), pr.get("duration"), bool(pr.get("finished"))
        return _card(m)

    @app.get("/api/art/{name}.jpg", dependencies=[need])
    def art_file(name: str):
        if not name.isalnum():
            raise HTTPException(404)
        f = library.art_dir / f"{name}.jpg"
        if not f.is_file():
            raise HTTPException(404)
        return FileResponse(f, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})

    @app.get("/api/transcript/{key}.{fmt}", dependencies=[need])
    def transcript(key: str, fmt: str, censor: bool = False):
        if fmt not in ("txt", "srt", "vtt") or not key.isalnum():
            raise HTTPException(404)
        loaded = tr.load_words(cfg.cache_dir, key)
        if not loaded:
            raise HTTPException(404, "Scan this title first: the transcript comes from the scan")
        _, words = loaded
        if censor:
            words = tr.mask(words, analyzer.wordlist.find(words))
        m = db.get_meta(key) or {}
        title = (db.get_filter(key) or {}).get("title") or m.get("title") or key
        body = {"srt": tr.to_srt, "vtt": tr.to_vtt}.get(fmt, lambda w: tr.to_txt(w, title))(words)
        stem = "".join(c for c in title if c.isalnum() or c in " -_.").strip() or key
        mime = {"srt": "application/x-subrip", "vtt": "text/vtt", "txt": "text/plain"}[fmt]
        return Response(body, media_type=f"{mime}; charset=utf-8", headers={
            "Content-Disposition": f'attachment; filename="{stem} transcript.{fmt}"'})

    @app.get("/api/captions/{source_id}/{item_id}", dependencies=[need])
    def captions(source_id: str, item_id: str):
        """Subtitle and caption tracks inside the file or next to it, plus the scan transcript."""
        ref = resolve(source_id, item_id)
        p = probe(source_id, item_id)
        key = media_key(source_id, item_id)
        out = [{"id": str(s.index), "label": s.label() or f"Track {s.index}", "where": "inside the file"}
               for s in p.subtitles]
        out += [{"id": f"side{i}", "label": Path(x).name, "where": "next to the file"}
                for i, x in enumerate(ref.subtitle_paths)]
        return {"tracks": out, "transcript": tr.load_words(cfg.cache_dir, key) is not None, "key": key}

    # ---- playback progress ------------------------------------------------------
    @app.post("/api/progress/{key}", dependencies=[need])
    def progress_save(key: str, body: dict = Body(...)):
        """Remember where someone is in a title. A POST so the browser can send it as the page closes."""
        if not key.isalnum():
            raise HTTPException(404)
        try:
            pos, dur = float(body.get("position", 0)), body.get("duration")
            dur = float(dur) if dur not in (None, "") else None
        except (TypeError, ValueError):
            raise HTTPException(400, "bad position")
        if not (0 <= pos < 1e7) or (dur is not None and not (0 < dur < 1e7)):
            raise HTTPException(400, "bad position")
        sid, iid = str(body.get("source_id", "")), str(body.get("item_id", ""))
        if not sid or not iid or media_key(sid, iid) != key:
            raise HTTPException(400, "source_id/item_id do not match this title")
        return db.save_progress(key, sid, iid, str(body.get("title", ""))[:300], pos, dur)

    @app.post("/api/progress/{key}/watched", dependencies=[need])
    def progress_watched(key: str, body: dict = Body(...)):
        """Mark a title watched or unwatched by hand."""
        m = db.get_meta(key) or {}
        if body.get("watched"):
            sid, iid = body.get("source_id") or m.get("source_id"), body.get("item_id") or m.get("item_id")
            if not sid or not iid or media_key(sid, iid) != key:
                raise HTTPException(400, "unknown title")
            existing = db.get_progress(key) or {}
            dur = existing.get("duration") or 1.0
            return db.save_progress(key, sid, iid, m.get("title") or str(body.get("title", ""))[:300], dur, dur)
        db.clear_progress(key)
        return {"position": 0.0, "finished": 0}

    @app.delete("/api/progress/{key}", dependencies=[need])
    def progress_clear(key: str):
        db.clear_progress(key)
        return {"ok": True}

    @app.get("/api/progress/recent", dependencies=[need])
    def progress_recent(limit: int = Query(20, ge=1, le=60)):
        """Titles to pick up again, newest first, with the artwork and names the library has."""
        out = []
        for p in db.recent_progress(limit):
            m = db.get_meta(p["media_key"]) or {}
            show = db.get_show(m["show_key"]) if m.get("show_key") else None
            title = (show["title"] if show else (m.get("title") or p["title"] or "Untitled"))
            sub = ""
            if show:
                sub = f"S{m.get('season', 0):02d}E{m.get('episode', 0):02d}" + (f" · {m['title']}" if m.get("title") else "")
            art = (f"/api/art/{p['media_key']}.jpg" if m.get("art") else
                   (f"/api/art/{m['show_key']}.jpg" if show and show.get("art") else None))
            out.append({"media_key": p["media_key"], "source_id": p["source_id"], "item_id": p["item_id"], "title": title,
                        "subtitle": sub, "art_url": art, "position": p["position"], "duration": p["duration"],
                        "fraction": min(1.0, p["position"] / p["duration"]) if p["duration"] else None})
        return out

    # ---- tidy file names -----------------------------------------------------
    @app.get("/api/rename/plan", dependencies=[need])
    def rename_plan(source_id: str, only_matched: bool = True, layout: str = "flat"):
        try:
            return renamer.plan(source_id, only_matched, layout)
        except RenameError as exc:
            raise HTTPException(400, str(exc))

    @app.post("/api/rename/apply", dependencies=[need])
    def rename_apply(body: dict = Body(...)):
        try:
            return renamer.apply(body["source_id"], [str(i) for i in body.get("ids", [])],
                                 bool(body.get("only_matched", True)), str(body.get("layout", "flat")))
        except RenameError as exc:
            raise HTTPException(400, str(exc))

    @app.get("/api/rename/batches", dependencies=[need])
    def rename_batches():
        return db.rename_batches()

    @app.post("/api/rename/undo/{batch}", dependencies=[need])
    def rename_undo(batch: str):
        try:
            return renamer.undo(batch)
        except RenameError as exc:
            raise HTTPException(400, str(exc))

    @app.get("/api/library/settings", dependencies=[need])
    def library_settings():
        return library.public_settings()

    @app.put("/api/library/settings", dependencies=[need])
    def library_settings_put(body: dict = Body(...)):
        try:
            return library.update_settings(body)
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @app.post("/api/library/settings/test", dependencies=[need])
    def library_settings_test():
        try:
            return {"message": library.test()}
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, f"Could not reach the details service: {exc}")

    @app.get("/api/library/candidates", dependencies=[need])
    def library_candidates(key: str, q: str = "", year: int | None = None):
        m = db.get_meta(key)
        if not m:
            raise HTTPException(404)
        title = q.strip() or (db.get_show(m["show_key"]) or {}).get("title") or m["title"]
        try:
            return library.candidates(m["kind"], title, year)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, f"Search failed: {exc}")

    @app.post("/api/library/title/{key}/match", dependencies=[need])
    def library_match(key: str, body: dict = Body(...)):
        try:
            return _card(library.apply_choice(key, body["candidate"]))
        except KeyError:
            raise HTTPException(404)
        except (ValueError, KeyError) as exc:
            raise HTTPException(400, str(exc))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, f"Could not fetch that entry: {exc}")

    # ---- live TV ---------------------------------------------------------------
    def _channel(c: dict) -> dict:
        return {"key": c["chan_key"], "name": c["name"], "groups": [g for g in (c["grp"] or "").split(";") if g],
                "logo_url": f"/api/live/logo/{c['chan_key']}" if c["logo"] else None, "item_id": c["item_id"], "letter": c["letter"],
                "favorite": bool(c["favorite"]), "failures": c["failures"]}

    @app.get("/api/live/channels", dependencies=[need])
    def live_channels(q: str = "", group: str = "", favorites: bool = False, hide_dead: bool = True,
                      letter: str = Query("", max_length=1), recent: bool = False,
                      limit: int = Query(120, ge=1, le=500), offset: int = Query(0, ge=0)):
        q = q.strip()
        rows = db.list_channels(q, group, favorites, hide_dead, limit, offset, letter.upper(), recent)
        return {"channels": [_channel(c) for c in rows],
                "total": db.count_channels(q, group, favorites, hide_dead, letter.upper(), recent),
                "letters": db.letter_counts(q, group, favorites, hide_dead), "stats": db.channel_stats()}

    @app.get("/api/live/groups", dependencies=[need])
    def live_groups():
        return db.channel_groups()

    @app.get("/api/live/logo/{key}", dependencies=[need])
    def live_logo(key: str):
        if not key.isalnum():
            raise HTTPException(404)
        f = livetv.logo_path(key)
        if not f:
            raise HTTPException(404)
        return FileResponse(f, media_type="image/png", headers={"Cache-Control": "private, max-age=604800"})

    @app.post("/api/live/channels/{key}/favorite", dependencies=[need])
    def live_favorite(key: str, body: dict = Body(...)):
        if not db.get_channel(key):
            raise HTTPException(404)
        db.set_favorite(key, bool(body.get("favorite")))
        return {"ok": True}

    @app.post("/api/live/channels/{key}/report", dependencies=[need])
    def live_report(key: str, body: dict = Body(...)):
        db.report_channel(key, bool(body.get("ok")))
        return {"ok": True}

    @app.get("/api/live/playlists", dependencies=[need])
    def live_playlists():
        return db.list_playlists()

    @app.post("/api/live/playlists", dependencies=[need])
    def live_playlist_add(body: dict = Body(...)):
        return livetv.add_playlist(str(body.get("name", "")), str(body.get("url", "")))

    @app.post("/api/live/playlists/import", dependencies=[need])
    def live_import():
        n = livetv.import_sources()
        for p in db.list_playlists():
            if not p["updated_at"]:
                try:
                    livetv.sync(p["id"])
                except SourceError:
                    pass
        return {"imported": n}

    @app.post("/api/live/playlists/{pid}/refresh", dependencies=[need])
    def live_playlist_refresh(pid: str):
        try:
            return {"channels": livetv.sync(pid)}
        except KeyError:
            raise HTTPException(404)

    @app.delete("/api/live/playlists/{pid}", dependencies=[need])
    def live_playlist_delete(pid: str):
        db.delete_playlist(pid)
        return {"ok": True}

    # ---- background tasks ---------------------------------------------------
    @app.get("/api/tasks", dependencies=[need])
    def tasks_list():
        return tasks.list()

    @app.put("/api/tasks/{task_id}", dependencies=[need])
    def tasks_update(task_id: str, body: dict = Body(...)):
        try:
            tasks.update(task_id, body)
        except KeyError:
            raise HTTPException(404)
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc))
        return tasks.list()

    @app.post("/api/tasks/{task_id}/run", dependencies=[need])
    def tasks_run(task_id: str):
        try:
            started = tasks.run(task_id)
        except KeyError:
            raise HTTPException(404)
        return {"started": started}

    @app.get("/api/jobs/state", dependencies=[need])
    def jobs_state():
        return {"paused": analyzer.paused}

    @app.post("/api/jobs/pause", dependencies=[need])
    def jobs_pause():
        analyzer.pause()
        return {"paused": True}

    @app.post("/api/jobs/resume", dependencies=[need])
    def jobs_resume():
        analyzer.resume()
        return {"paused": False}

    @app.post("/api/jobs/stop-all", dependencies=[need])
    def jobs_stop_all():
        return {"stopped": analyzer.stop_all()}

    @app.post("/api/jobs/retry-failed", dependencies=[need])
    def jobs_retry_failed():
        return {"queued": analyzer.retry_failed()}

    @app.post("/api/jobs/{job_id}/restart", dependencies=[need])
    def jobs_restart(job_id: str):
        job = analyzer.restart(job_id)
        if not job:
            raise HTTPException(404)
        return job

    @app.get("/api/jobs", dependencies=[need])
    def jobs():
        return db.list_jobs()

    @app.get("/api/jobs/{job_id}", dependencies=[need])
    def job(job_id: str):
        j = db.get_job(job_id)
        if not j:
            raise HTTPException(404)
        return j

    @app.post("/api/jobs/{job_id}/cancel", dependencies=[need])
    def cancel(job_id: str):
        analyzer.cancel(job_id)
        return {"ok": True}

    return app
