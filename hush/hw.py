"""Finds a GPU video encoder in this machine, so transcoding does not have to use the CPU."""
from __future__ import annotations

import functools
import os
import shutil
import subprocess

VAAPI_DEVICES = ("/dev/dri/renderD128", "/dev/dri/renderD129")


@functools.lru_cache(maxsize=4)
def detect(ffmpeg: str = "ffmpeg") -> dict:
    """The best encoder this machine can use: {"encoder", "device", "gpu"}. Falls back to the CPU (libx264)."""
    try:
        encoders = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        encoders = ""
    if "h264_nvenc" in encoders and (os.path.exists("/dev/nvidiactl") or shutil.which("nvidia-smi")):
        return {"encoder": "h264_nvenc", "device": None, "gpu": "NVIDIA (NVENC)"}
    dev = next((d for d in VAAPI_DEVICES if os.path.exists(d)), None)
    if dev and "h264_vaapi" in encoders:
        return {"encoder": "h264_vaapi", "device": dev, "gpu": "Intel/AMD (VAAPI)"}
    return {"encoder": "libx264", "device": None, "gpu": ""}


def encoder_for(cfg) -> dict:
    """What to encode with: the configured encoder, or the best one found when it is "auto"."""
    want = (cfg.video_encoder or "auto").strip()
    if want == "auto":
        return detect(cfg.ffmpeg)
    dev = next((d for d in VAAPI_DEVICES if os.path.exists(d)), VAAPI_DEVICES[0]) if want.endswith("vaapi") else None
    return {"encoder": want, "device": dev, "gpu": "" if want == "libx264" else want}
