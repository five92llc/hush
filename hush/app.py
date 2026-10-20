"""Hush HTTP API + web UI."""
from __future__ import annotations

import dataclasses
import json
import logging
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from . import discover, epg, hw, media, mylist, profiles as rules, stream, weather
from .hls import HLSError, HLSManager
from .livefilter import LiveFilter, LiveFilterError
from .live import LiveTV
from .remote import RemoteHub
from .analysis.jobs import Analyzer
from .auth import COOKIE, SESSION_TTL, Auth
from .config import Config, load_config
from .db import DB
from .qbit import Qbit, QbitError
from .sources import Registry, SourceError, discover_dlna, media_key
from .library import art, transcript as tr
from .library.rename import RenameError, Renamer
from .library.service import MetadataService
from .notify import Notifier
from .tasks import TaskManager
from .sources.base import enc

log = logging.getLogger("hush")
WEB = Path(__file__).parent / "web"


class FreshStatic(StaticFiles):
    """Static files that browsers must re-check on every use (cheap: unchanged files answer 304).
    Without this Safari kept running an old app.js after an update."""

    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        resp.headers["Cache-Control"] = "no-cache"
        return resp


_STATIC_REF = re.compile(r'((?:src|href|data-modern|data-legacy)=")/static/([^"?#]+)(")')


def versioned_page(name: str) -> HTMLResponse:
    """An HTML page whose /static/... links carry the file's change time, so an updated script or style
    sheet is fetched at once instead of being taken from the browser's cache."""
    def stamp(m):
        f = WEB / m.group(2)
        v = int(f.stat().st_mtime) if f.is_file() else 0
        return f"{m.group(1)}/static/{m.group(2)}?v={v}{m.group(3)}"
    return HTMLResponse(_STATIC_REF.sub(stamp, (WEB / name).read_text(encoding="utf-8")), headers={"Cache-Control": "no-cache"})
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
    livefilter = LiveFilter(cfg, analyzer.wordlist, cfg.data_dir / "livefilter")
    livetv = LiveTV(cfg, db, registry)
    remote = RemoteHub()
    renamer = Renamer(db, registry)
    renamer.cache_dir, renamer.art_dir = cfg.cache_dir, library.art_dir
    tasks = TaskManager(cfg, db, registry, analyzer, library, livetv)
    notifier = Notifier(db)

    def downloads_finished(names: list[str]) -> None:
        notifier.event("download", "Download finished", ", ".join(names[:3]) + (f" and {len(names) - 3} more" if len(names) > 3 else ""))
        threading.Timer(30, tasks.refresh_all).start()           # give the files a moment to settle, then add them to the library
    qb = Qbit(db, downloads_finished)
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
        qb.watch()
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

    # ---- profiles: who is watching ------------------------------------------------------
    PROFILE_COOKIE = "hush_profile"

    def default_profile() -> dict:
        everyone = db.list_profiles()
        return next((p for p in everyone if not p["kids"]), everyone[0])

    def get_profile(request: Request) -> dict:
        pid = request.cookies.get(PROFILE_COOKIE)
        return (db.get_profile(pid) if pid else None) or default_profile()

    def need_adult(prof: dict = Depends(get_profile)) -> dict:
        if prof["kids"]:
            raise HTTPException(403, "Ask a grown-up to do that")
        return prof

    def title_ok(prof: dict, key: str) -> bool:
        return not prof["kids"] or rules.approved(prof, db.title_facts(key))

    def episode_ok(prof: dict, row: dict, show_cert: str | None) -> bool:
        return rules.approved(prof, {"cert": row.get("cert"), "show_cert": show_cert, "flags": row.get("flags"), "scanned": row.get("scanned")})

    KIDS_BLOCKED = ("/api/dlna", "/api/network", "/api/open-url", "/api/analyze", "/api/scan-folder", "/api/jobs", "/api/tasks",
                    "/api/notifications", "/api/qbit", "/api/library/settings", "/api/library/candidates", "/api/rename", "/api/password",
                    "/api/browse", "/api/live/playlists", "/api/transcript", "/api/weather/search", "/api/weather/location")
    ITEM_PATHS = {"media", "raw", "stream", "seekpoint", "subtitle", "sidecars", "captions", "external", "filtered"}

    def kids_refusal(prof: dict, method: str, path: str) -> str | None:
        """Why a kids profile may not make this request, or None. Backs up the hidden buttons: the server decides."""
        cfg = rules.kid_settings(prof)
        if path.startswith(KIDS_BLOCKED):
            return "That is for grown-ups"
        if path.startswith("/api/sources") and method != "GET":
            return "That is for grown-ups"
        if path.startswith("/api/live") and not cfg["allow_live"]:
            return "Live TV is switched off for this profile"
        if path.startswith("/api/library/title/") and method != "GET":
            return "That is for grown-ups"
        segs = path.split("/")                       # ['', 'api', kind, a, b, ...]
        kind = segs[2] if len(segs) > 2 else ""
        src = item = None
        if kind in ITEM_PATHS and len(segs) > 4:
            src, item = segs[3], segs[4].removesuffix(".mkv")
        elif kind == "hls" and len(segs) > 5 and segs[3] == "start":
            src, item = segs[4], segs[5]
        if src == "url" and kind in ("stream", "hls", "raw", "external", "filtered"):
            return "Live TV on this profile always plays through the language filter"
        if src is not None:
            if src == "url" and cfg["allow_live"]:
                return None
            return None if title_ok(prof, media_key(src, item)) else "This title is not available on this profile"
        if kind == "filters" and len(segs) > 3:
            if method != "GET" or len(segs) > 4:
                return "That is for grown-ups"
            return None if title_ok(prof, segs[3]) else "This title is not available on this profile"
        if kind == "progress" and len(segs) > 3 and segs[3] != "recent":
            return None if title_ok(prof, segs[3]) else "This title is not available on this profile"
        if kind == "art" and len(segs) > 3:
            key = segs[3].removesuffix(".jpg")
            if db.title_facts(key):
                return None if title_ok(prof, key) else "Not available"
            eps = [e for e in db.episode_facts() if e["show_key"] == key]
            show = db.get_show(key) or {}
            return None if any(rules.approved(prof, {**e, "show_cert": show.get("cert")}) for e in eps) else "Not available"
        return None

    @app.middleware("http")
    async def profile_guard(request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/") and not path.startswith(("/api/session", "/api/login", "/api/logout", "/api/profiles", "/api/config", "/api/client-error")):
            prof = get_profile(request)
            if prof["kids"]:
                why = await run_in_threadpool(kids_refusal, prof, request.method, path)
                if why:
                    return JSONResponse({"detail": why}, status_code=403)
        return await call_next(request)

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
        remote = bool(ref.url) and not ref.path
        if remote and (saved := db.get_probe(source_id, item_id, 7 * 86400)):       # channels and links: remembered across restarts
            result = cache.put(key, media.ProbeResult.from_saved(saved))
            if result.duration is None:
                ref.live = True
            return result
        try:
            result = cache.put(key, media.probe(cfg.ffprobe, ref, source_id, item_id))
            if remote:
                db.save_probe(source_id, item_id, dataclasses.asdict(result))
            if result.duration is None and ref.url and not ref.live:
                ref.live = True          # a stream with no length (IPTV channel): no seeking, scanning or filtering
            return result
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, f"Could not read media: {exc}")

    # ---- pages & session ------------------------------------------------
    app.mount("/static", FreshStatic(directory=WEB), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return versioned_page("index.html")

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
        return {"encoder": hw.encoder_for(cfg), "engines": analyzer.engines(), "categories": analyzer.wordlist.categories_info(),
                "source_types": ["local", "smb", "ftp", "sftp", "http", "dlna", "jellyfin", "plex"]}

    # ---- sources --------------------------------------------------------
    @app.get("/api/sources", dependencies=[need])
    def list_sources(prof: dict = Depends(get_profile)):
        return [] if prof["kids"] else registry.list()

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
    def browse(source_id: str, dir: str = "", prof: dict = Depends(get_profile)):
        entries = [e.to_dict(source_id) for e in registry.get(source_id).browse(dir)]
        keys = [e["media_key"] for e in entries if "media_key" in e]
        done = db.filtered_keys(keys)
        prog = db.progress_map(prof["id"], keys)
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
    def media_info(source_id: str, item_id: str, audio: int | None = None, hevc: int = 0, prof: dict = Depends(get_profile)):
        ref = resolve(source_id, item_id)
        p = probe(source_id, item_id)
        key = media_key(source_id, item_id)
        f = db.get_filter(key)
        prog = db.get_progress(prof["id"], key)
        resume = ({"position": prog["position"], "finished": bool(prog["finished"])}
                  if prog and not ref.live else None)
        return {"title": ref.title, "kind": "video" if p.video else "audio", "name": ref.name,
                "live": ref.live, "resume": resume, "media_key": key, "probe": p.to_dict(), "mode": media.choose_mode(ref, p, audio, hevc),
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
        cmd, mime = stream.build_ffmpeg_cmd(cfg, ref, source_id, item_id, mode, max(0.0, start), audio,
                                            vcodec=p.video[0].codec if p.video else None)
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
                mute_ranges=ranges, container="hls", hls_dir=d, vcodec=p.video[0].codec if p.video else None)[0], owner=tab[:40])
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

    # ---- weather for the "tuning in" screen ----------------------------------------------
    @app.get("/api/weather", dependencies=[need])
    def weather_now():
        loc = db.get_setting("weather", None)
        if not loc:
            return {"configured": False}
        try:
            return {"configured": True, "place": loc["name"], "lat": loc["lat"], "lon": loc["lon"], **weather.current(loc["lat"], loc["lon"], loc.get("unit", "c"))}
        except httpx.HTTPError:
            return {"configured": True, "place": loc["name"], "unavailable": True}

    @app.get("/api/weather/search", dependencies=[need])
    def weather_search(q: str):
        if len(q.strip()) < 2:
            return []
        try:
            return weather.search(q.strip())
        except httpx.HTTPError:
            raise HTTPException(502, "Could not reach the weather service")

    @app.put("/api/weather/location", dependencies=[need])
    def weather_location(body: dict = Body(...)):
        if not body.get("name"):
            db.set_setting("weather", None)
            return {"configured": False}
        try:
            loc = {"name": str(body["name"])[:80], "lat": float(body["lat"]), "lon": float(body["lon"]), "unit": "f" if body.get("unit") == "f" else "c"}
        except (KeyError, ValueError):
            raise HTTPException(400, "Choose a place from the list")
        db.set_setting("weather", loc)
        return weather_now()

    # ---- live TV language filter (captions) ----------------------------------------------
    @app.post("/api/livefilter/open", dependencies=[need])
    def livefilter_open(body: dict = Body(...), prof: dict = Depends(get_profile)):
        """Start (or join) the filtered, 10-second-delayed feed of a live channel. Waits until it can be played."""
        src, item = str(body.get("src", "")), str(body.get("item", ""))
        ref = resolve(src, item)
        if not ref.live and not ref.url:
            raise HTTPException(400, "Only live channels use the live filter")
        cats = {c for c in str(body.get("cats", "")).split(",") if c} or None
        if prof["kids"]:
            cats = None                                            # a kids profile always gets everything filtered
        try:
            sess = livefilter.open(media_key(src, item), media.ffmpeg_input(ref, src, item), cats, str(body.get("tab", ""))[:40], bool(prof["kids"]))
        except LiveFilterError as exc:
            raise HTTPException(502, str(exc))
        return {"sid": sess.sid, "hls": f"/api/livefilter/{sess.sid}/index.m3u8", "mp4": f"/api/livefilter/{sess.sid}/stream.mp4", "status": sess.status()}

    @app.post("/api/livefilter/release", dependencies=[need])
    def livefilter_release(body: dict = Body(default={})):
        livefilter.release(str(body.get("tab", ""))[:40])
        return {"ok": True}

    @app.get("/api/livefilter/{sid}/status", dependencies=[need])
    def livefilter_status(sid: str):
        s = livefilter.get(sid)
        if not s:
            raise HTTPException(404)
        return s.status()

    @app.get("/api/livefilter/{sid}/{name}", dependencies=[need])
    async def livefilter_file(request: Request, sid: str, name: str):
        s = livefilter.get(sid)
        if not s:
            raise HTTPException(404)
        if name == "stream.mp4":                                   # for browsers that cannot play HLS: repackage the filtered feed
            if not (s.out / "index.m3u8").exists():
                raise HTTPException(404)
            s.last = time.time()
            cmd = [cfg.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-fflags", "+genpts", "-i", str(s.out / "index.m3u8"),
                   "-c", "copy", "-movflags", "frag_keyframe+empty_moov+default_base_moof", "-f", "mp4", "pipe:1"]
            return await stream.ffmpeg_response(request, cmd, "video/mp4")
        f = livefilter.file(sid, name)
        if not f:
            raise HTTPException(404)
        if name.endswith(".m3u8"):
            return FileResponse(f, media_type="application/vnd.apple.mpegurl", headers={"Cache-Control": "no-store"})
        return FileResponse(f, media_type="video/mp2t", headers={"Cache-Control": "private, max-age=60"})

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
        m["fanart_url"] = f"/api/fanart/{m['media_key']}.jpg" if m.get("fanart") else None
        m["scanned"] = bool(m.get("scanned"))
        m["watched"] = bool(m.get("watched"))
        return m

    warming: set[tuple[str, str]] = set()

    @app.post("/api/live/warm", dependencies=[need])
    def live_warm(body: dict = Body(...)):
        """Look at the neighbouring channels ahead of time so zapping to them starts quickly."""
        items = [(str(i.get("src", "")), str(i.get("item", ""))) for i in (body.get("items") or [])[:3]]

        def work(src: str, item: str) -> None:
            try:
                probe(src, item)
            except Exception:  # noqa: BLE001 - a channel that does not answer is simply not warmed
                pass
            finally:
                warming.discard((src, item))
        for src, item in items:
            if src == "url" and (src, item) not in warming and not cache.get(("probe", src, item)):
                warming.add((src, item))
                threading.Thread(target=work, args=(src, item), daemon=True).start()
        return {"ok": True}

    @app.get("/api/library/version", dependencies=[need])
    def library_version():
        return {"version": db.library_version()}

    @app.get("/api/library/movies", dependencies=[need])
    def library_movies(prof: dict = Depends(get_profile)):
        return [_card(m) for m in db.list_movies(prof["id"]) if not prof["kids"] or rules.approved(prof, m)]

    @app.get("/api/library/shows", dependencies=[need])
    def library_shows(prof: dict = Depends(get_profile)):
        shown_eps: dict[str, int] = {}
        if prof["kids"]:                                     # a show is there only for the episodes this profile may watch
            certs = {s["show_key"]: s.get("cert") for s in db.list_shows(prof["id"])}
            for e in db.episode_facts():
                if rules.approved(prof, {**e, "show_cert": certs.get(e["show_key"])}):
                    shown_eps[e["show_key"]] = shown_eps.get(e["show_key"], 0) + 1
        out = []
        for s in db.list_shows(prof["id"]):
            if prof["kids"]:
                if not shown_eps.get(s["show_key"]):
                    continue
                s["episodes"] = shown_eps[s["show_key"]]
            s["art_url"] = f"/api/art/{s['show_key']}.jpg" if s.get("art") else None
            s["scanned"] = int(s.get("scanned") or 0)
            s["watched"] = int(s.get("watched") or 0)
            out.append(s)
        return out

    def _upc(rows: list[dict]) -> list[dict]:
        return [{"show_key": r["show_key"], "show_title": r["show_title"], "season": r["season"], "episode": r["episode"],
                 "title": r["title"], "airs_at": r["airs_at"], "overview": r["overview"], "runtime": r["runtime"],
                 "art_url": f"/api/art/{r['show_key']}.jpg" if r.get("show_art") else None} for r in rows]

    # ---- my list -----------------------------------------------------------------
    def _watch_items(prof: dict) -> list[dict]:
        """Everything this profile follows: what they added, plus shows they have started watching."""
        shows = {s["show_key"]: s for s in library_shows(prof)}                 # only shows this profile may see
        rows = {r["ref"]: r for r in db.list_watch(prof["id"])}
        for key, s in shows.items():                                              # started watching: counts as Watching until told otherwise
            if f"show:{key}" not in rows and (s.get("watched") or 0) > 0:
                rows[f"show:{key}"] = {"ref": f"show:{key}", "kind": "show", "status": "watching", "auto": True, "updated_at": 0, "extra": {}}
        items = []
        for ref, r in rows.items():
            item = {"ref": ref, "kind": r["kind"], "status": r["status"], "auto": bool(r.get("auto")), "updated_at": r["updated_at"]}
            if ref.startswith("show:"):
                key = ref[5:]
                s = shows.get(key)
                if not s:
                    continue
                prog = mylist.library_progress(db.episodes_of(key, prof["id"]))
                up = db.list_upcoming(key, limit=1)
                item.update(title=s["title"], year=s.get("year"), art_url=s.get("art_url"), in_library=True, show_key=key, progress=prog,
                            airing=({"season": up[0]["season"], "episode": up[0]["episode"], "title": up[0]["title"], "airs_at": up[0]["airs_at"]} if up else None))
            elif ref.startswith("movie:"):
                m = db.get_meta(ref[6:])
                if not m or not title_ok(prof, ref[6:]):
                    continue
                prog = db.get_progress(prof["id"], m["media_key"])
                item.update(title=m["title"], year=m.get("year"), art_url=f"/api/art/{m['media_key']}.jpg" if m.get("art") else None, in_library=True,
                            media_key=m["media_key"], source_id=m["source_id"], item_id=m["item_id"],
                            watched=bool(prog and prog["finished"]), position=(prog or {}).get("position", 0))
            elif ref.startswith("tm:") and not prof["kids"]:
                info = mylist.next_airing(ref[3:])
                item.update(title=r["title"], year=r["year"], in_library=False, tvmaze_id=ref[3:], network=r["extra"].get("network", ""),
                            art_url=f"/api/art/{r['art_key']}.jpg" if r.get("art_key") and (library.art_dir / f"{r['art_key']}.jpg").exists() else None,
                            airing=info["next"], show_status=info["status"])
            else:
                continue
            items.append(item)
        return items

    # ---- qBittorrent ------------------------------------------------------------------
    def _qb(fn):
        try:
            return fn()
        except QbitError as exc:
            raise HTTPException(502, str(exc))
        except httpx.HTTPError as exc:
            raise HTTPException(502, f"qBittorrent: {exc}")

    @app.get("/api/qbit", dependencies=[need])
    def qbit_status():
        s = qb.public()
        if not s["configured"]:
            return {**s, "connected": False}
        try:
            return {**s, "connected": True, "version": qb.version(), "torrents": qb.torrents()}
        except (QbitError, httpx.HTTPError) as exc:
            return {**s, "connected": False, "error": str(exc)}

    @app.put("/api/qbit/settings", dependencies=[need])
    def qbit_settings(body: dict = Body(...)):
        return _qb(lambda: qb.update(body))

    @app.post("/api/qbit/torrents/{h}/{action}", dependencies=[need])
    def qbit_action(h: str, action: str):
        _qb(lambda: qb.act(h, action))
        return {"ok": True}

    @app.get("/api/qbit/rss", dependencies=[need])
    def qbit_rss():
        def go():
            r = qb.rss()
            have = {t["hash"].lower() for t in qb.torrents()}
            for f in r["feeds"]:
                for a in f["articles"]:
                    a["in_client"] = bool(qb.btih(a["url"]) and qb.btih(a["url"]) in have)
                    a.pop("url", None)                                    # the page never needs the link itself
            return r
        return _qb(go)

    @app.get("/api/qbit/categories", dependencies=[need])
    def qbit_categories():
        return _qb(qb.categories)

    @app.post("/api/qbit/add", dependencies=[need])
    def qbit_add(body: dict = Body(...)):
        _qb(lambda: qb.add(str(body.get("url", "")), str(body.get("category", "")), str(body.get("save_path", ""))))
        return {"ok": True}

    @app.post("/api/qbit/category/{h}", dependencies=[need])
    def qbit_category(h: str, body: dict = Body(...)):
        _qb(lambda: qb.set_category(h, str(body.get("category", ""))))
        return {"ok": True}

    @app.post("/api/qbit/location/{h}", dependencies=[need])
    def qbit_location(h: str, body: dict = Body(...)):
        _qb(lambda: qb.set_location(h, str(body.get("path", ""))))
        return {"ok": True}

    @app.post("/api/qbit/rss/add", dependencies=[need])
    def qbit_rss_add(body: dict = Body(...)):
        title = _qb(lambda: qb.add_from_feed(str(body.get("feed", "")), str(body.get("id", "")),
                                             str(body.get("category", "")), str(body.get("save_path", ""))))
        return {"ok": True, "title": title}

    @app.post("/api/qbit/rss/refresh", dependencies=[need])
    def qbit_rss_refresh(body: dict = Body(...)):
        _qb(lambda: qb.refresh_feed(str(body.get("name", ""))))
        return {"ok": True}

    @app.get("/api/watchlist", dependencies=[need])
    def watchlist(prof: dict = Depends(get_profile)):
        return _watch_items(prof)

    @app.get("/api/watchlist/search", dependencies=[need])
    def watchlist_search(q: str, prof: dict = Depends(get_profile)):
        if prof["kids"] or len(q.strip()) < 2:
            return []
        try:
            return mylist.search_shows(q.strip())
        except httpx.HTTPError:
            raise HTTPException(502, "Could not reach TVmaze")

    @app.post("/api/watchlist", dependencies=[need])
    def watchlist_set(body: dict = Body(...), prof: dict = Depends(get_profile)):
        status = str(body.get("status", "planned"))
        if status not in mylist.STATUSES:
            raise HTTPException(400, "Unknown status")
        if body.get("tvmaze_id"):                              # a show that is not in the library
            if prof["kids"]:
                raise HTTPException(403, "Ask a grown-up to add shows")
            tid = str(body["tvmaze_id"])
            if not tid.isdigit():
                raise HTTPException(400, "Bad show")
            ref = f"tm:{tid}"
            if not db.get_watch(prof["id"], ref):
                try:
                    info = mylist.show_info(tid)
                except httpx.HTTPError:
                    raise HTTPException(502, "Could not reach TVmaze")
                key = mylist.art_key(ref)
                if info["poster_url"]:
                    art.from_url(cfg.ffmpeg, info["poster_url"], library.art_dir / f"{key}.jpg")
                db.save_watch(prof["id"], ref, "show", status, info["title"], info["year"], key, {"network": info["network"]})
                return {"ok": True, "ref": ref}
        elif body.get("show_key"):
            ref = f"show:{body['show_key']}"
            show = db.get_show(str(body["show_key"]))
            if not show:
                raise HTTPException(404)
            db.save_watch(prof["id"], ref, "show", status, show["title"], show.get("year"))
            return {"ok": True, "ref": ref}
        elif body.get("media_key"):
            ref = f"movie:{body['media_key']}"
            m = db.get_meta(str(body["media_key"]))
            if not m:
                raise HTTPException(404)
            db.save_watch(prof["id"], ref, "movie", status, m["title"], m.get("year"))
            return {"ok": True, "ref": ref}
        else:
            ref = str(body.get("ref", ""))
            if not db.get_watch(prof["id"], ref):
                raise HTTPException(404)
        w = db.get_watch(prof["id"], ref)
        db.save_watch(prof["id"], ref, w["kind"], status, w["title"], w["year"], w.get("art_key") or "", w["extra"])
        return {"ok": True, "ref": ref}

    @app.delete("/api/watchlist", dependencies=[need])
    def watchlist_remove(ref: str, prof: dict = Depends(get_profile)):
        db.delete_watch(prof["id"], ref)
        return {"ok": True}

    @app.get("/api/library/upcoming", dependencies=[need])
    def library_upcoming(prof: dict = Depends(get_profile)):
        """Episodes of the shows in the library that have not aired yet, soonest first."""
        visible = {s["show_key"] for s in library_shows(prof)}
        return _upc([r for r in db.list_upcoming(limit=200) if r["show_key"] in visible])[:40]

    @app.get("/api/library/shows/{show_key}", dependencies=[need])
    def library_show(show_key: str, prof: dict = Depends(get_profile)):
        show = db.get_show(show_key)
        if not show:
            raise HTTPException(404)
        eps = [e for e in db.episodes_of(show_key, prof["id"]) if not prof["kids"] or episode_ok(prof, e, show.get("cert"))]
        if prof["kids"] and not eps:
            raise HTTPException(404)
        show["art_url"] = f"/api/art/{show_key}.jpg" if show.get("art") else None
        show["fanart_url"] = f"/api/fanart/{show_key}.jpg" if show.get("fanart") else None
        w = db.get_watch(prof["id"], f"show:{show_key}")
        return {"show": show, "episodes": [_card(e) for e in eps], "upcoming": _upc(db.list_upcoming(show_key)),
                "list_status": w["status"] if w else None}

    @app.get("/api/library/title/{key}", dependencies=[need])
    def library_title(key: str, prof: dict = Depends(get_profile)):
        m = db.get_meta(key)
        if not m or not title_ok(prof, key):
            raise HTTPException(404)
        m["scanned"] = bool(db.get_filter(key))
        pr = db.get_progress(prof["id"], key) or {}
        m["position"], m["duration"], m["watched"] = pr.get("position"), pr.get("duration"), bool(pr.get("finished"))
        w = db.get_watch(prof["id"], f"movie:{key}")
        m["list_status"] = w["status"] if w else None
        return _card(m)

    thumb_lock = threading.Lock()

    def thumb_of(src: Path, w: int, kind: str) -> Path:
        """A smaller copy of an image for grids (cards need ~300 px, not the full poster); made once, then reused."""
        w = min((160, 240, 320, 480), key=lambda x: abs(x - w))
        dst = cfg.data_dir / "art" / "thumbs" / f"{src.stem}-{w}.{kind}"
        if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
            return dst
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.stem + ".tmp." + kind)
        args = ["-q:v", "5"] if kind == "jpg" else []
        with thumb_lock:
            r = subprocess.run([cfg.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(src), "-frames:v", "1",
                                "-vf", f"scale='min({w},iw)':-2", *args, str(tmp)], capture_output=True, timeout=30)
        if r.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
            tmp.unlink(missing_ok=True)
            return src
        tmp.replace(dst)
        return dst

    @app.get("/api/art/{name}.jpg", dependencies=[need])
    def art_file(name: str, w: int = 0):
        if not name.isalnum():
            raise HTTPException(404)
        f = library.art_dir / f"{name}.jpg"
        if not f.is_file():
            raise HTTPException(404)
        if w:
            f = thumb_of(f, w, "jpg")
        return FileResponse(f, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})

    @app.get("/api/fanart/{name}.jpg", dependencies=[need])
    def fanart_file(name: str):
        f = art.fanart_path(library.art_dir, name) if name.isalnum() else None
        if not f or not f.is_file():
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

    # ---- errors from browsers (a smart TV has no console) ------------------------------------
    recent_client_errors: dict[str, list[float]] = {}

    @app.post("/api/client-error", include_in_schema=False)
    async def client_error(request: Request):
        """Scripts in the browser report their errors here, so a blank TV screen shows up in the server log.
        No login needed (it can fail before one); small, rate limited, and only logged."""
        ip = request.client.host if request.client else "?"
        now = time.time()
        stamps = [t for t in recent_client_errors.get(ip, []) if now - t < 60]
        if len(stamps) >= 20:
            return Response(status_code=204)
        recent_client_errors[ip] = stamps + [now]
        try:
            data = json.loads((await request.body())[:4000])
            info = {k: str(data.get(k, ""))[:400] for k in ("kind", "message", "file", "line", "col", "stack", "ua", "hash")}
        except (ValueError, AttributeError):
            return Response(status_code=204)
        log.warning("client error from %s: %s", ip, json.dumps(info))
        return Response(status_code=204)

    # ---- profiles ---------------------------------------------------------------------
    def _set_profile_cookie(resp, request: Request, pid: str) -> None:
        resp.set_cookie(PROFILE_COOKIE, pid, max_age=365 * 86400, httponly=True, samesite="lax", secure=request.url.scheme == "https")

    @app.get("/api/profiles", dependencies=[need])
    def profiles_list(request: Request):
        everyone = db.list_profiles()
        cookie = request.cookies.get(PROFILE_COOKIE)
        valid = any(p["id"] == cookie for p in everyone)
        current = next((p for p in everyone if p["id"] == cookie), None) or default_profile()
        return {"profiles": [rules.public(p) for p in everyone], "current": rules.public(current),
                "needs_pick": len(everyone) > 1 and not valid, "can_manage": not current["kids"],
                "lock": bool(db.get_setting("profiles_lock", False)) and auth.enabled,
                "categories": list(rules.CATEGORIES), "colors": list(rules.COLORS), "avatars": list(rules.AVATARS)}

    @app.post("/api/profiles/select", dependencies=[need])
    def profiles_select(request: Request, body: dict = Body(...)):
        target = db.get_profile(str(body.get("id", "")))
        if not target:
            raise HTTPException(404, "No such profile")
        here = get_profile(request)
        if (here["kids"] and not target["kids"] and here["id"] != target["id"]
                and db.get_setting("profiles_lock", False) and auth.enabled):
            if not auth.check_password(str(body.get("password", "")), request.client.host if request.client else "?"):
                raise HTTPException(403, "Enter the Hush password to leave a kids profile")
        resp = JSONResponse({"ok": True, "profile": rules.public(target)})
        _set_profile_cookie(resp, request, target["id"])
        return resp

    def _profile_fields(body: dict, existing: dict | None = None) -> tuple[str, bool, str, dict, str]:
        name = str(body.get("name", existing["name"] if existing else "")).strip()[:24]
        if not name:
            raise HTTPException(400, "Give the profile a name")
        kids = bool(body.get("kids", existing["kids"] if existing else False))
        color = str(body.get("color") or (existing or {}).get("color") or rules.COLORS[len(db.list_profiles()) % len(rules.COLORS)])
        if color not in rules.COLORS:
            color = rules.COLORS[0]
        settings = dict((existing or {}).get("settings") or {})
        if kids and isinstance(body.get("settings"), dict):
            try:
                settings.update(rules.clean_settings(body["settings"]))
            except (TypeError, ValueError):
                raise HTTPException(400, "Those settings are not valid")
        avatar = str(body.get("avatar", (existing or {}).get("avatar") or ""))
        if avatar and avatar not in rules.AVATARS:
            raise HTTPException(400, "Pick one of the pictures")
        return name, kids, color, settings if kids else {}, avatar

    @app.post("/api/profiles", dependencies=[need])
    def profiles_create(body: dict = Body(...), _adult: dict = Depends(need_adult)):
        if len(db.list_profiles()) >= 12:
            raise HTTPException(400, "That is the most profiles Hush keeps (12)")
        name, kids, color, settings, avatar = _profile_fields(body)
        if any(p["name"].lower() == name.lower() for p in db.list_profiles()):
            raise HTTPException(400, "A profile with that name already exists")
        pid = "p" + uuid.uuid4().hex[:8]
        db.save_profile(pid, name, kids, color, settings, avatar)
        return rules.public(db.get_profile(pid))

    @app.put("/api/profiles/lock", dependencies=[need])
    def profiles_lock(body: dict = Body(...), _adult: dict = Depends(need_adult)):
        db.set_setting("profiles_lock", bool(body.get("lock")))
        return {"lock": bool(body.get("lock")) and auth.enabled}

    @app.put("/api/profiles/{pid}", dependencies=[need])
    def profiles_update(pid: str, body: dict = Body(...), _adult: dict = Depends(need_adult)):
        existing = db.get_profile(pid)
        if not existing:
            raise HTTPException(404)
        name, kids, color, settings, avatar = _profile_fields(body, existing)
        if kids and not existing["kids"] and not any(p["id"] != pid and not p["kids"] for p in db.list_profiles()):
            raise HTTPException(400, "There must be at least one grown-up profile")
        if any(p["id"] != pid and p["name"].lower() == name.lower() for p in db.list_profiles()):
            raise HTTPException(400, "A profile with that name already exists")
        db.save_profile(pid, name, kids, color, settings, avatar)
        return rules.public(db.get_profile(pid))

    @app.delete("/api/profiles/{pid}", dependencies=[need])
    def profiles_delete(pid: str, _adult: dict = Depends(need_adult)):
        victim = db.get_profile(pid)
        if not victim:
            raise HTTPException(404)
        if not victim["kids"] and not any(p["id"] != pid and not p["kids"] for p in db.list_profiles()):
            raise HTTPException(400, "There must be at least one grown-up profile")
        db.delete_profile(pid)
        return {"ok": True}

    # ---- phone remote ---------------------------------------------------------------
    @app.get("/remote", include_in_schema=False)
    def remote_page():
        return versioned_page("remote.html")

    @app.websocket("/api/remote/ws")
    async def remote_ws(ws: WebSocket):
        if auth.enabled and not auth.valid_session(ws.cookies.get(COOKIE)):
            await ws.close(code=4401)
            return
        await ws.accept()
        role, sid = None, None
        try:
            while True:
                msg = await ws.receive_json()
                kind = msg.get("type") if isinstance(msg, dict) else None
                if kind == "hello" and role is None:
                    role = "screen" if msg.get("role") == "screen" else "remote"
                    sid = remote.clean_id(msg.get("id"))
                    if role == "screen":
                        await remote.add_screen(sid, str(msg.get("name") or "Screen"), ws)
                    else:
                        await remote.add_remote(ws)
                elif kind == "state" and role == "screen" and isinstance(msg.get("state"), dict):
                    await remote.update_state(sid, msg["state"])
                elif kind == "cmd" and role == "remote":
                    ok = await remote.send_cmd(str(msg.get("to", "")), str(msg.get("cmd", "")), msg.get("args") or {})
                    if not ok:
                        await ws.send_json({"type": "error", "message": "That screen is not connected", "to": msg.get("to")})
                elif kind == "ping":
                    await ws.send_json({"type": "pong"})
        except (WebSocketDisconnect, RuntimeError, ValueError):
            pass
        finally:
            await remote.remove(ws, role, sid)

    # ---- playback progress ------------------------------------------------------
    @app.post("/api/progress/{key}", dependencies=[need])
    def progress_save(key: str, body: dict = Body(...), prof: dict = Depends(get_profile)):
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
        return db.save_progress(prof["id"], key, sid, iid, str(body.get("title", ""))[:300], pos, dur)

    @app.post("/api/progress/{key}/watched", dependencies=[need])
    def progress_watched(key: str, body: dict = Body(...), prof: dict = Depends(get_profile)):
        """Mark a title watched or unwatched by hand."""
        m = db.get_meta(key) or {}
        if body.get("watched"):
            sid, iid = body.get("source_id") or m.get("source_id"), body.get("item_id") or m.get("item_id")
            if not sid or not iid or media_key(sid, iid) != key:
                raise HTTPException(400, "unknown title")
            existing = db.get_progress(prof["id"], key) or {}
            dur = existing.get("duration") or 1.0
            return db.save_progress(prof["id"], key, sid, iid, m.get("title") or str(body.get("title", ""))[:300], dur, dur)
        db.clear_progress(prof["id"], key)
        return {"position": 0.0, "finished": 0}

    @app.delete("/api/progress/{key}", dependencies=[need])
    def progress_clear(key: str, prof: dict = Depends(get_profile)):
        db.clear_progress(prof["id"], key)
        return {"ok": True}

    @app.get("/api/progress/recent", dependencies=[need])
    def progress_recent(limit: int = Query(20, ge=1, le=60), prof: dict = Depends(get_profile)):
        """Titles to pick up again, newest first, with the artwork and names the library has."""
        out = []
        for p in db.recent_progress(prof["id"], limit * 3 if prof["kids"] else limit):
            if prof["kids"] and not title_ok(prof, p["media_key"]):
                continue
            if len(out) >= limit:
                break
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
                      limit: int = Query(120, ge=1, le=500), offset: int = Query(0, ge=0), prof: dict = Depends(get_profile)):
        q, pid = q.strip(), prof["id"]
        rows = db.list_channels(q, group, favorites, hide_dead, limit, offset, letter.upper(), recent, pid)
        return {"channels": [_channel(c) for c in rows],
                "total": db.count_channels(q, group, favorites, hide_dead, letter.upper(), recent, pid),
                "letters": db.letter_counts(q, group, favorites, hide_dead, pid), "stats": db.channel_stats(pid)}

    @app.get("/api/live/guides", dependencies=[need])
    def live_guides():
        return {"urls": db.get_setting("epg_urls", []), "advertised": db.epg_urls(), "presets": epg.PRESETS,
                "status": db.get_setting("epg_status", None)}

    @app.post("/api/live/guides", dependencies=[need])
    def live_guide_add(body: dict = Body(...)):
        try:
            return {"urls": livetv.add_guide(str(body.get("url", "")))}
        except SourceError as exc:
            raise HTTPException(400, str(exc))

    @app.delete("/api/live/guides", dependencies=[need])
    def live_guide_remove(url: str):
        return {"urls": livetv.remove_guide(url)}

    @app.post("/api/live/guides/refresh", dependencies=[need])
    def live_guide_refresh():
        livetv.guide_async()
        return {"ok": True}

    @app.get("/api/live/epg", dependencies=[need])
    def live_epg(keys: str = ""):
        """What is on now and next, for up to 80 channels at once."""
        return db.epg_now_next([k for k in keys.split(",") if k.isalnum()][:80])

    @app.get("/api/live/groups", dependencies=[need])
    def live_groups():
        return db.channel_groups()

    @app.get("/api/live/logo/{key}", dependencies=[need])
    def live_logo(key: str, w: int = 0):
        if not key.isalnum():
            raise HTTPException(404)
        f = livetv.logo_path(key)
        if not f:
            raise HTTPException(404)
        if w:
            f = thumb_of(f, w, "png")
        return FileResponse(f, media_type="image/png", headers={"Cache-Control": "private, max-age=604800"})

    snap_slots = threading.Semaphore(2)

    @app.get("/api/live/snapshot/{key}.jpg", dependencies=[need])
    def live_snapshot(key: str):
        """One frame from a channel, for a quick look before tuning in. Kept for a few minutes; at most two at a time."""
        ch = db.get_channel(key) if key.isalnum() else None
        if not ch:
            raise HTTPException(404)
        dst = cfg.data_dir / "art" / "snaps" / f"{key}.jpg"
        headers = {"Cache-Control": "private, max-age=300"}
        if dst.exists() and time.time() - dst.stat().st_mtime < 600:
            return FileResponse(dst, media_type="image/jpeg", headers=headers)
        if not snap_slots.acquire(blocking=False):
            raise HTTPException(503, "Busy")
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            ref = resolve("url", ch["item_id"])
            cmd = [cfg.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-fflags", "+nobuffer",
                   "-analyzeduration", "1500000", "-probesize", "1500000", *media.ffmpeg_input(ref, "url", ch["item_id"]),
                   "-frames:v", "1", "-vf", "scale=320:-2", "-q:v", "6", str(dst)]
            try:
                subprocess.run(cmd, capture_output=True, timeout=12)
            except subprocess.TimeoutExpired:
                dst.unlink(missing_ok=True)
        finally:
            snap_slots.release()
        if not dst.exists() or dst.stat().st_size == 0:
            raise HTTPException(404)
        return FileResponse(dst, media_type="image/jpeg", headers=headers)

    @app.get("/api/live/alternates/{key}", dependencies=[need])
    def live_alternates(key: str):
        """Other working channels with the same name (another source of the same channel), for when one stops playing."""
        ch = db.get_channel(key) if key.isalnum() else None
        if not ch:
            raise HTTPException(404)
        def norm(n: str) -> str:
            n = re.sub(r"[\[(].*?[\])]", " ", n.lower())
            n = re.sub(r"\b(hd|fhd|uhd|sd|4k|hevc|h265|h264|1080p?|720p?|backup|alt)\b", " ", n)
            return re.sub(r"[^a-z0-9]+", "", n)
        want = norm(ch["name"])
        if len(want) < 3:
            return []
        rows = db._all("SELECT chan_key, name, item_id FROM channels WHERE failures<2 AND chan_key!=? AND name LIKE ?",
                       (key, f"%{ch['name'].strip()[:3]}%"))
        return [{"key": r["chan_key"], "item_id": r["item_id"], "name": r["name"]} for r in rows if norm(r["name"]) == want][:5]

    @app.post("/api/live/channels/{key}/favorite", dependencies=[need])
    def live_favorite(key: str, body: dict = Body(...), prof: dict = Depends(get_profile)):
        if not db.get_channel(key):
            raise HTTPException(404)
        db.set_favorite(key, bool(body.get("favorite")), prof["id"])
        return {"ok": True}

    @app.post("/api/live/channels/{key}/report", dependencies=[need])
    def live_report(key: str, body: dict = Body(...), prof: dict = Depends(get_profile)):
        db.report_channel(key, bool(body.get("ok")), prof["id"])
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
            n = livetv.sync(pid)
            livetv.guide_async()
            return {"channels": n}
        except KeyError:
            raise HTTPException(404)

    @app.delete("/api/live/playlists/{pid}", dependencies=[need])
    def live_playlist_delete(pid: str):
        db.delete_playlist(pid)
        return {"ok": True}

    # ---- background tasks ---------------------------------------------------
    @app.post("/api/library/refresh", dependencies=[need])
    def library_refresh():
        """The Refresh button: look through every source, add new titles and artwork, update upcoming episodes."""
        return {"started": tasks.refresh_all()}

    @app.get("/api/library/refresh", dependencies=[need])
    def library_refresh_status():
        return {"running": tasks.refreshing, "result": tasks.refresh_result}

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
