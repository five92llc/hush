"""Byte-range serving and live FFmpeg transcoding."""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import AsyncIterator

import httpx
from fastapi import Request
from fastapi.responses import Response, StreamingResponse
from starlette.concurrency import run_in_threadpool

from . import hw
from .media import FFMPEG_SEEK_BACKOFF, ffmpeg_input
from .sources.base import MediaRef

log = logging.getLogger("hush.stream")
CHUNK = 256 * 1024
_RANGE = re.compile(r"bytes=(\d*)-(\d*)")


def _parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    if not header:
        return None
    m = _RANGE.match(header.strip())
    if not m:
        return None
    s, e = m.groups()
    if s == "":                       # suffix range: last N bytes
        n = int(e)
        return max(0, size - n), size - 1
    start = int(s)
    end = int(e) if e else size - 1
    if start >= size:
        raise ValueError("unsatisfiable")
    return start, min(end, size - 1)


async def serve_raw(request: Request, ref: MediaRef) -> Response:
    """Serve original bytes with HTTP Range support (direct play + loopback)."""
    if ref.native:
        return Response(status_code=404, content="this link is only readable through a live stream")
    if ref.url:
        return await _proxy(request, ref)

    size = ref.size if ref.size is not None else (os.path.getsize(ref.path) if ref.path else None)
    if size is None:
        return Response(status_code=500, content="size unknown")
    try:
        rng = _parse_range(request.headers.get("range"), size)
    except ValueError:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
    start, end = rng if rng else (0, size - 1)
    length = end - start + 1

    def opener():
        return open(ref.path, "rb") if ref.path else ref.opener()

    async def body() -> AsyncIterator[bytes]:
        fh = await run_in_threadpool(opener)
        try:
            await run_in_threadpool(fh.seek, start)
            remaining = length
            while remaining > 0:
                chunk = await run_in_threadpool(fh.read, min(CHUNK, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk
        finally:
            await run_in_threadpool(fh.close)

    headers = {"Accept-Ranges": "bytes", "Content-Length": str(length),
               "Cache-Control": "private, max-age=3600"}
    if rng:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return StreamingResponse(body(), status_code=206 if rng else 200,
                             media_type=ref.mime, headers=headers)


async def _proxy(request: Request, ref: MediaRef) -> Response:
    """Pass-through proxy for HTTP-backed sources, forwarding Range."""
    headers = dict(ref.headers)
    if request.headers.get("range"):
        headers["Range"] = request.headers["range"]
    client = httpx.AsyncClient(timeout=httpx.Timeout(30, read=120), follow_redirects=True)
    req = client.build_request("GET", ref.url, headers=headers)
    try:
        upstream = await client.send(req, stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        return Response(status_code=502, content=f"upstream error: {exc}")

    async def body():
        try:
            async for chunk in upstream.aiter_raw(CHUNK):
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    passthrough = {k: v for k, v in upstream.headers.items()
                   if k.lower() in ("content-length", "content-range", "accept-ranges", "last-modified", "etag")}
    passthrough.setdefault("Accept-Ranges", "bytes")
    ctype = upstream.headers.get("content-type", "")
    if not ctype or ctype.startswith(("application/octet-stream", "binary/")):
        ctype = ref.mime
    return StreamingResponse(body(), status_code=upstream.status_code, media_type=ctype,
                             headers=passthrough)


def mute_filter(ranges: list[dict], offset: float = 0.0) -> str | None:
    """FFmpeg audio filter that silences enabled ranges (times relative to ``offset``)."""
    parts = []
    for r in ranges:
        if not r.get("enabled", True):
            continue
        s, e = r["start"] - offset, r["end"] - offset
        if e <= 0:
            continue
        parts.append(f"between(t,{max(0.0, s):.3f},{e:.3f})")
    if not parts:
        return None
    return f"volume=enable='{'+'.join(parts)}':volume=0"


def _hls_output(ref: MediaRef, folder) -> list[str]:
    """Segment and playlist options. A live source gets a sliding window; anything else a growing list."""
    out = ["-f", "hls", "-hls_time", "2" if ref.live else "4", "-hls_segment_type", "mpegts",
           "-hls_segment_filename", str(folder / "seg%05d.ts")]
    if ref.live:
        out += ["-hls_list_size", "6", "-hls_flags", "delete_segments+independent_segments"]
    else:
        out += ["-hls_list_size", "0", "-hls_playlist_type", "event", "-hls_flags", "independent_segments"]
    return out + [str(folder / "index.m3u8")]


def build_ffmpeg_cmd(cfg, ref: MediaRef, source_id: str, item_id: str, mode: str,
                     start: float = 0.0, audio_index: int | None = None,
                     mute_ranges: list[dict] | None = None, container: str = "mp4",
                     hls_dir=None, vcodec: str | None = None) -> tuple[list[str], str]:
    """Return (argv, mime) for a live stream of this item."""
    cmd = [cfg.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin"]
    if ref.live:
        start, mute_ranges = 0.0, None   # live links cannot seek or be filtered
    enc = hw.encoder_for(cfg)
    if cfg.hwaccel and mode == "transcode":
        cmd += ["-hwaccel", cfg.hwaccel]
    if mode == "transcode" and enc["encoder"].endswith("vaapi"):
        cmd += ["-vaapi_device", enc["device"]]
    if start > 0:
        if mode == "remux":
            # ``start`` is a keyframe from media.keyframe_before(). Stream copy
            # can only begin on a keyframe, so seek just past it (undoing
            # ffmpeg's B-frame back-off) and start every stream there.
            cmd += ["-noaccurate_seek", "-ss", f"{start + FFMPEG_SEEK_BACKOFF + 0.01:.3f}"]
        else:
            cmd += ["-ss", f"{start:.3f}"]
    if ref.live:                       # start a channel as soon as the first frames arrive
        cmd += ["-fflags", "+nobuffer+discardcorrupt", "-analyzeduration", "1500000", "-probesize", "1500000"]
    cmd += ffmpeg_input(ref, source_id, item_id)

    afilter = mute_filter(mute_ranges, start) if mute_ranges else None

    if mode == "audio":
        cmd += ["-map", f"0:{audio_index}" if audio_index is not None else "0:a:0", "-vn", "-sn"]
        if afilter:
            cmd += ["-af", afilter]
        if container == "hls":
            return cmd + ["-c:a", "aac", "-b:a", "192k", "-ac", "2", *_hls_output(ref, hls_dir)], "application/vnd.apple.mpegurl"
        cmd += ["-c:a", "libmp3lame", "-b:a", "192k", "-f", "mp3", "pipe:1"]
        return cmd, "audio/mpeg"

    cmd += ["-map", "0:v:0", "-map", f"0:{audio_index}?" if audio_index is not None else "0:a:0?", "-sn", "-dn"]
    if mode == "remux":
        cmd += ["-c:v", "copy"]
        if vcodec in ("hevc", "h265"):
            cmd += ["-tag:v", "hvc1"]        # the tag browsers and TVs need to accept HEVC in MP4
    else:
        e, scale = enc["encoder"], "scale='min(1920,iw)':-2"
        cmd += ["-c:v", e]
        if e == "libx264":
            cmd += ["-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
                    "-profile:v", "high", "-g", "48", *(["-tune", "zerolatency"] if ref.live else [])]
        elif e == "h264_nvenc":
            cmd += ["-preset", "p4", "-cq", "23", "-pix_fmt", "yuv420p", "-profile:v", "high", "-g", "48",
                    *(["-tune", "ll"] if ref.live else [])]
        elif e.endswith("vaapi"):
            cmd += ["-qp", "23", "-g", "48"]
            scale += ",format=nv12,hwupload"
        cmd += ["-vf", scale]
    if afilter:
        cmd += ["-af", afilter]
    cmd += ["-c:a", "aac", "-b:a", "192k", "-ac", "2"]
    if container == "hls":
        return cmd + _hls_output(ref, hls_dir), "application/vnd.apple.mpegurl"
    if container == "matroska":   # for external players (VLC, Kodi, TVs)
        cmd += ["-f", "matroska", "pipe:1"]
        return cmd, "video/x-matroska"
    cmd += ["-movflags", "frag_keyframe+empty_moov+default_base_moof", "-frag_duration", "1000000",
            "-f", "mp4", "pipe:1"]
    return cmd, "video/mp4"


async def ffmpeg_response(request: Request, cmd: list[str], mime: str) -> StreamingResponse:
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

    async def drain_stderr():  # keep the pipe from filling; log the tail
        tail = b""
        while line := await proc.stderr.readline():
            tail = (tail + line)[-2000:]
        if tail.strip() and proc.returncode not in (0, None, -9):
            log.warning("ffmpeg: %s", tail.decode(errors="ignore").strip())
    asyncio.create_task(drain_stderr())

    async def body() -> AsyncIterator[bytes]:
        try:
            while True:
                chunk = await proc.stdout.read(CHUNK)
                if not chunk:
                    break
                yield chunk
                if await request.is_disconnected():
                    break
        finally:
            if proc.returncode is None:
                proc.kill()
            await proc.wait()

    return StreamingResponse(body(), media_type=mime,
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
