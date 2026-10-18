"""Posters and thumbnails, kept as small JPEGs in data/art/<key>.jpg."""
from __future__ import annotations

import subprocess
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .providers import IMAGE_HOSTS, UA

WIDTH = 480        # posters and thumbnails are scaled to this width


def art_path(art_dir: Path, key: str) -> Path:
    return art_dir / f"{key}.jpg"


def _scale(ffmpeg: str, src: str, dst: Path, extra_in: list[str] | None = None) -> bool:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".tmp.jpg")
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *(extra_in or []), "-i", src,
           "-frames:v", "1", "-vf", f"scale='min({WIDTH},iw)':-2", "-q:v", "4", str(tmp)]
    try:
        subprocess.run(cmd, capture_output=True, timeout=90, check=True)
    except (subprocess.SubprocessError, OSError):
        tmp.unlink(missing_ok=True)
        return False
    if not tmp.exists() or tmp.stat().st_size == 0:
        tmp.unlink(missing_ok=True)
        return False
    tmp.replace(dst)
    return True


def from_file(ffmpeg: str, image: Path, dst: Path) -> bool:
    return _scale(ffmpeg, str(image), dst)


def from_url(ffmpeg: str, url: str, dst: Path, client: httpx.Client | None = None) -> bool:
    host = urlparse(url).hostname or ""
    if urlparse(url).scheme != "https" or host not in IMAGE_HOSTS:
        return False
    try:
        r = (client or httpx).get(url, timeout=20, headers=UA, follow_redirects=False)
        r.raise_for_status()
    except httpx.HTTPError:
        return False
    if not r.headers.get("content-type", "").startswith("image/") or len(r.content) > 8_000_000:
        return False
    raw = dst.with_suffix(".src")
    dst.parent.mkdir(parents=True, exist_ok=True)
    raw.write_bytes(r.content)
    try:
        return _scale(ffmpeg, str(raw), dst)
    finally:
        raw.unlink(missing_ok=True)


def from_video(ffmpeg: str, input_args: list[str], duration: float | None, dst: Path) -> bool:
    """A frame from about a tenth of the way in (skips logos and black openings)."""
    at = min(600.0, (duration or 0) * 0.1)
    for t in (at, 5.0):
        args = input_args[:]
        i = args.index("-i")
        if _scale(ffmpeg, args[i + 1], dst, extra_in=[*args[:i], "-ss", f"{t:.1f}"]):
            return True
    return False
