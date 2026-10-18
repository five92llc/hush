"""Probing media and deciding how the browser can play it.

Play modes:
  direct    - browser plays the original bytes (range requests, instant seek)
  remux     - video copied, audio re-encoded to AAC, wrapped in fragmented MP4
              (cheap; typical for MKV with H.264)
  transcode - full re-encode to H.264/AAC fragmented MP4 (HEVC, MPEG-2, AVI/DivX...)
  audio     - audio-only re-encode to MP3 (WMA, APE, AIFF...)
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from typing import Any

from .sources.base import MediaRef

_runtime: dict[str, Any] = {"loopback": "http://127.0.0.1:8642", "internal_token": ""}

BROWSER_VIDEO = {"h264", "vp8", "vp9", "av1"}
BROWSER_AUDIO = {"aac", "mp3", "opus", "vorbis", "flac"}
DIRECT_CONTAINERS = {
    ".mp4": ("mov", "mp4"), ".m4v": ("mov", "mp4"), ".mov": ("mov",), ".webm": ("webm", "matroska"),
    ".ogv": ("ogg",), ".mp3": ("mp3",), ".m4a": ("mov", "mp4"), ".aac": ("aac",),
    ".ogg": ("ogg",), ".oga": ("ogg",), ".opus": ("ogg",), ".flac": ("flac",), ".wav": ("wav",),
}


def configure(loopback: str, internal_token: str) -> None:
    _runtime["loopback"] = loopback.rstrip("/")
    _runtime["internal_token"] = internal_token


def loopback_url(source_id: str, item_id: str) -> str:
    return (f"{_runtime['loopback']}/internal/raw/{source_id}/{item_id}"
            f"?k={_runtime['internal_token']}")


def ffmpeg_input(ref: MediaRef, source_id: str, item_id: str) -> list[str]:
    """Input arguments that let ffmpeg/ffprobe read this item."""
    if ref.path:
        return ["-i", ref.path]
    if ref.url:
        args = []
        if ref.headers:
            args += ["-headers", "".join(f"{k}: {v}\r\n" for k, v in ref.headers.items())]
        if not ref.url.lower().split("?")[0].endswith((".m3u8", ".mpd")):
            args += ["-reconnect", "1", "-reconnect_on_network_error", "1",
                     "-reconnect_delay_max", "5"]
        return args + ["-i", ref.url]
    # SMB and other opener-based sources: ffmpeg reads through our own
    # authenticated loopback range endpoint, so seeking still works.
    return ["-i", loopback_url(source_id, item_id)]


@dataclass
class Stream:
    index: int
    type: str
    codec: str
    language: str = ""
    title: str = ""
    channels: int = 0
    default: bool = False

    def label(self) -> str:
        bits = [self.language.upper() if self.language else "", self.title, self.codec]
        if self.channels:
            bits.append({1: "mono", 2: "stereo", 6: "5.1", 8: "7.1"}.get(self.channels, f"{self.channels}ch"))
        return " · ".join(b for b in bits if b)


@dataclass
class ProbeResult:
    duration: float | None
    format_names: tuple[str, ...]
    video: list[Stream] = field(default_factory=list)
    audio: list[Stream] = field(default_factory=list)
    subtitles: list[Stream] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        f = lambda ss: [{"index": s.index, "codec": s.codec, "language": s.language,  # noqa: E731
                          "label": s.label(), "default": s.default} for s in ss]
        return {"duration": self.duration, "format": list(self.format_names),
                "video": f(self.video), "audio": f(self.audio), "subtitles": f(self.subtitles)}


TEXT_SUB_CODECS = {"subrip", "ass", "ssa", "webvtt", "mov_text", "text"}


def probe(ffprobe: str, ref: MediaRef, source_id: str, item_id: str, timeout: int = 60) -> ProbeResult:
    cmd = [ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
           *ffmpeg_input(ref, source_id, item_id)]
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=timeout, check=True).stdout
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ffprobe failed: {exc.stderr.decode(errors='ignore')[-400:]}") from exc
    data = json.loads(out or b"{}")
    fmt = data.get("format", {})
    dur = fmt.get("duration")
    res = ProbeResult(duration=float(dur) if dur else None,
                      format_names=tuple((fmt.get("format_name") or "").split(",")))
    for s in data.get("streams", []):
        tags = s.get("tags", {})
        st = Stream(index=s["index"], type=s.get("codec_type", ""), codec=s.get("codec_name", "?"),
                    language=tags.get("language", "") if tags.get("language") != "und" else "",
                    title=tags.get("title", ""), channels=s.get("channels", 0),
                    default=bool(s.get("disposition", {}).get("default")))
        if st.type == "video" and not s.get("disposition", {}).get("attached_pic"):
            res.video.append(st)
        elif st.type == "audio":
            res.audio.append(st)
        elif st.type == "subtitle" and st.codec in TEXT_SUB_CODECS:
            res.subtitles.append(st)
    return res


def choose_mode(ref: MediaRef, p: ProbeResult, audio_index: int | None = None) -> str:
    vcodec = p.video[0].codec if p.video else None
    a = next((s for s in p.audio if s.index == audio_index), p.audio[0] if p.audio else None)
    acodec = a.codec if a else None
    a_ok = acodec is None or acodec in BROWSER_AUDIO or (acodec.startswith("pcm_") and ref.ext == ".wav")
    first_audio = not p.audio or audio_index is None or audio_index == p.audio[0].index
    is_hls = ref.ext in (".m3u8", ".mpd")

    if not p.video:  # audio only
        if ref.ext in DIRECT_CONTAINERS and a_ok and not is_hls:
            return "direct"
        return "audio"
    if (ref.ext in DIRECT_CONTAINERS and vcodec in BROWSER_VIDEO and a_ok and first_audio
            and not is_hls and any(f in p.format_names for f in DIRECT_CONTAINERS[ref.ext])):
        return "direct"
    if vcodec in ("h264", "vp9", "av1"):  # all three are valid in fragmented MP4
        return "remux"
    return "transcode"


# ffmpeg pulls -ss back by 3/23 s for streams with B-frames before seeking, so
# the probe mimics that and the stream request adds it back (see stream.py).
FFMPEG_SEEK_BACKOFF = 3 / 23


def keyframe_before(ffprobe: str, ref: MediaRef, source_id: str, item_id: str, t: float) -> float:
    """Where a stream-copy seek to ``t`` will really land (a video keyframe).

    Remuxing copies the video stream, which can only start on a keyframe, so
    the player asks for the landing time first and offsets its clock by it.
    """
    if t <= 0.2:
        return 0.0
    target = max(0.0, t - FFMPEG_SEEK_BACKOFF)
    cmd = [ffprobe, "-v", "error", "-select_streams", "v:0",
           "-read_intervals", f"{target:.3f}%+#1",
           "-show_entries", "packet=pts_time,dts_time", "-of", "csv=p=0",
           *ffmpeg_input(ref, source_id, item_id)]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout
    except subprocess.TimeoutExpired:
        return t
    for line in out.split():
        for v in line.split(","):
            try:
                return max(0.0, float(v))
            except ValueError:
                continue
    return t
