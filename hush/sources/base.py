"""Common source abstraction.

Every source (local disk, SMB share, HTTP, DLNA, Jellyfin, Plex) exposes the
same two operations:

* ``browse(dir_id)`` -> list of Entry (folders and playable files)
* ``resolve(item_id)`` -> MediaRef describing how to read the bytes

Item ids are opaque strings owned by the source; the web UI never builds them.
"""
from __future__ import annotations

import base64
import hashlib
import mimetypes
from dataclasses import dataclass, field
from typing import IO, Any, Callable

VIDEO_EXT = {".mp4", ".m4v", ".mkv", ".webm", ".avi", ".mov", ".wmv", ".flv",
             ".mpg", ".mpeg", ".ts", ".m2ts", ".mts", ".3gp", ".3g2", ".ogv", ".vob", ".divx",
             ".m2v", ".mpe", ".asf", ".f4v", ".rm", ".rmvb", ".ogm", ".mxf", ".trp", ".tp",
             ".wtv", ".dvr-ms", ".nsv", ".amv", ".evo", ".qt", ".mjpeg", ".h264", ".hevc"}
AUDIO_EXT = {".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg", ".oga", ".opus",
             ".wma", ".aiff", ".aif", ".alac", ".ape", ".mka", ".ac3", ".eac3", ".dts",
             ".mp2", ".mpc", ".wv", ".tta", ".dsf", ".dff", ".caf", ".au", ".amr", ".m4b",
             ".m4r", ".weba", ".spx", ".ra", ".mid", ".midi"}
SUB_EXT = {".srt", ".vtt", ".ass", ".ssa", ".sub"}


def classify(name: str) -> str | None:
    """Return 'video', 'audio' or None for a file name."""
    lower = name.lower()
    dot = lower.rfind(".")
    if dot < 0:
        return None
    ext = lower[dot:]
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    return None


def enc(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def dec(value: str) -> str:
    pad = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + pad).decode()


def media_key(source_id: str, item_id: str) -> str:
    return hashlib.sha1(f"{source_id}\x00{item_id}".encode()).hexdigest()[:20]


@dataclass
class Entry:
    id: str
    name: str
    kind: str                  # dir | video | audio
    size: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    source: str | None = None  # set when the item belongs to another source (playlist entries)

    def to_dict(self, source_id: str) -> dict[str, Any]:
        sid = self.source or source_id
        d = {"id": self.id, "name": self.name, "kind": self.kind,
             "size": self.size, "meta": self.meta}
        if self.source:
            d["source_id"] = self.source
        if self.kind != "dir":
            d["media_key"] = media_key(sid, self.id)
        return d


@dataclass
class MediaRef:
    """How to read one media item.

    Exactly one access style is set:
      * ``path``   - a local filesystem path
      * ``url``    - an HTTP(S) URL, or a ``native`` one that only ffmpeg can read (``headers`` sent with every request)
      * ``opener`` - a callable returning a seekable binary file object (SMB)
    """
    title: str
    kind: str                                   # video | audio
    path: str | None = None
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    opener: Callable[[], IO[bytes]] | None = None
    size: int | None = None
    name: str = ""                              # original file name, for mime/ext
    subtitle_paths: list[str] = field(default_factory=list)  # sidecar subs (local only)
    subtitle_openers: list[Callable[[], IO[bytes]]] = field(default_factory=list)
    native: bool = False    # url is read by ffmpeg itself (ftp, rtmp, rtsp...); Hush cannot proxy it
    live: bool = False      # no fixed length or seeking, and it cannot be scanned

    @property
    def ext(self) -> str:
        n = (self.name or self.path or self.url or "").split("?")[0].lower()
        dot = n.rfind(".")
        return n[dot:] if dot >= 0 else ""

    @property
    def mime(self) -> str:
        overrides = {".mkv": "video/x-matroska", ".m4a": "audio/mp4", ".flac": "audio/flac",
                     ".opus": "audio/ogg", ".ts": "video/mp2t", ".webm": "video/webm",
                     ".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4v": "video/mp4"}
        if self.ext in overrides:
            return overrides[self.ext]
        guess, _ = mimetypes.guess_type("x" + self.ext)
        return guess or "application/octet-stream"


class SourceError(Exception):
    pass


class Source:
    type: str = "base"

    def __init__(self, conf: dict[str, Any]):
        self.conf = conf
        self.id: str = conf["id"]
        self.name: str = conf.get("name") or self.id

    def info(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "type": self.type,
                "editable": bool(self.conf.get("_runtime"))}

    def browse(self, dir_id: str = "") -> list[Entry]:
        raise NotImplementedError

    def resolve(self, item_id: str) -> MediaRef:
        raise NotImplementedError

    def close(self) -> None:
        pass


def sort_entries(entries: list[Entry]) -> list[Entry]:
    return sorted(entries, key=lambda e: (e.kind != "dir", e.name.lower()))
