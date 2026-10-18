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
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from . import media, stream
from .analysis.jobs import Analyzer
from .auth import COOKIE, SESSION_TTL, Auth
from .config import Config, load_config
from .db import DB
from .sources import Registry, SourceError, discover_dlna, media_key
from .sources.base import enc
from .sources.http import check_url_allowed

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
    auth = Auth(cfg.password, cfg.secret_key)
    registry = Registry(cfg.sources, db)
    media.configure(f"http://127.0.0.1:{cfg.port}", auth.internal_token)
    analyzer = Analyzer(cfg, db, registry)
    cache = Cache()

    # Restore the ad-hoc URL list.
    registry.get("url").urls = db.get_setting("recent_urls", [])

    app = FastAPI(title="Hush", docs_url=None, redoc_url=None)
    app.state.cfg, app.state.db, app.state.analyzer = cfg, db, analyzer

    @app.on_event("startup")
    def _start():
        analyzer.start()
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
            return cache.put(key, media.probe(cfg.ffprobe, ref, source_id, item_id))
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

    @app.post("/api/logout")
    def logout():
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(COOKIE)
        return resp

    @app.get("/api/config", dependencies=[need])
    def config_info():
        return {"engines": analyzer.engines(), "categories": analyzer.wordlist.categories_info(),
                "source_types": ["local", "smb", "http", "dlna", "jellyfin", "plex"]}

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

    @app.get("/api/dlna/discover", dependencies=[need])
    def dlna_discover():
        return discover_dlna()

    @app.get("/api/browse/{source_id}", dependencies=[need])
    def browse(source_id: str, dir: str = ""):
        entries = [e.to_dict(source_id) for e in registry.get(source_id).browse(dir)]
        done = db.filtered_keys([e["media_key"] for e in entries if "media_key" in e])
        for e in entries:
            if "media_key" in e:
                e["filtered"] = e["media_key"] in done
        return entries

    @app.post("/api/open-url", dependencies=[need])
    def open_url(body: dict = Body(...)):
        url = str(body.get("url", "")).strip()
        check_url_allowed(url)
        src = registry.get("url")
        recent = [u for u in src.urls if u["url"] != url]
        recent.insert(0, {"name": body.get("name") or url.rsplit("/", 1)[-1] or url, "url": url})
        src.urls = recent[:30]
        db.set_setting("recent_urls", src.urls)
        return {"source_id": "url", "item_id": enc(url)}

    # ---- media ----------------------------------------------------------
    @app.get("/api/media/{source_id}/{item_id}", dependencies=[need])
    def media_info(source_id: str, item_id: str, audio: int | None = None):
        ref = resolve(source_id, item_id)
        p = probe(source_id, item_id)
        key = media_key(source_id, item_id)
        f = db.get_filter(key)
        return {"title": ref.title, "kind": "video" if p.video else "audio", "name": ref.name,
                "media_key": key, "probe": p.to_dict(), "mode": media.choose_mode(ref, p, audio),
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

    @app.get("/api/seekpoint/{source_id}/{item_id}", dependencies=[need])
    def seekpoint(source_id: str, item_id: str, t: float, mode: str = "remux"):
        """Where a live stream requested at ``t`` will actually start."""
        if mode != "remux" or t <= 0:
            return {"start": max(0.0, t)}
        ref = resolve(source_id, item_id)
        return {"start": round(media.keyframe_before(cfg.ffprobe, ref, source_id, item_id, t), 3)}

    @app.get("/api/subtitle/{source_id}/{item_id}/{track}", dependencies=[need])
    def subtitle(source_id: str, item_id: str, track: str):
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
               "-f", "webvtt", "pipe:1"]
        try:
            out = subprocess.run(cmd, capture_output=True, timeout=900, check=True).stdout
        except subprocess.SubprocessError as exc:
            raise HTTPException(502, f"subtitle extraction failed: {exc}")
        return Response(out, media_type="text/vtt; charset=utf-8",
                        headers={"Cache-Control": "private, max-age=3600"})

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
        registry.get(source_id)
        engine = body.get("engine")
        if engine not in (None, "auto", "whisper", "subtitles"):
            raise HTTPException(400, "bad engine")
        title = body.get("title") or ""
        return analyzer.submit(source_id, item_id, title, None if engine in (None, "auto") else engine)

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
