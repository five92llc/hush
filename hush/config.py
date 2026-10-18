"""Configuration loading.

Config comes from a YAML file (HUSH_CONFIG, default ./config.yaml). Any string
value of the form ``${ENV_VAR}`` is replaced from the environment so secrets
(SMB passwords, Plex/Jellyfin tokens) never need to live in the file.
"""
from __future__ import annotations

import os
import re
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _expand(value: Any) -> Any:
    if isinstance(value, str):
        return _ENV_RE.sub(lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, list):
        return [_expand(v) for v in value]
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    return value


@dataclass
class AnalysisConfig:
    engine: str = "auto"            # auto | whisper | subtitles
    whisper_model: str = "small.en"  # tiny.en, base.en, small.en, medium.en, large-v3
    whisper_device: str = "auto"     # auto | cpu | cuda
    whisper_compute_type: str = "int8"
    whisper_cpu_threads: int = 0     # CPU threads per scan; 0 = library default (4)
    whisper_beam_size: int = 5       # 1 is about twice as fast, slightly less accurate
    language: str | None = "en"
    pad_before: float = 0.12         # seconds of extra mute before a word
    pad_after: float = 0.15          # seconds of extra mute after a word
    merge_gap: float = 0.35          # merge ranges closer than this
    workers: int = 1
    wordlist: str | None = None      # path to a custom wordlist YAML
    auto_scan: list[str] = field(default_factory=list)   # source ids to keep prescanned
    auto_scan_hours: float = 6       # how often auto_scan looks for new titles


@dataclass
class Config:
    data_dir: Path = Path("./data")
    host: str = "0.0.0.0"
    port: int = 8642
    password: str = ""
    secret_key: str = ""
    public_url: str = ""            # used to build links for external players
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"
    hwaccel: str = ""               # e.g. "vaapi", "cuda" (passed to -hwaccel)
    video_encoder: str = "auto"       # "auto" uses a GPU when one is found, else libx264
    sources: list[dict[str, Any]] = field(default_factory=list)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "hush.db"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"


def load_config(path: str | os.PathLike | None = None) -> Config:
    path = Path(path or os.environ.get("HUSH_CONFIG", "config.yaml"))
    raw: dict[str, Any] = {}
    if path.exists():
        raw = yaml.safe_load(path.read_text()) or {}
    raw = _expand(raw)

    analysis = AnalysisConfig(**(raw.pop("analysis", None) or {}))
    data_dir = Path(raw.pop("data_dir", os.environ.get("HUSH_DATA", "./data")))
    cfg = Config(data_dir=data_dir, analysis=analysis, **raw)

    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    cfg.cache_dir.mkdir(parents=True, exist_ok=True)

    if not cfg.password:
        cfg.password = os.environ.get("HUSH_PASSWORD", "")
    if not cfg.secret_key:
        key_file = cfg.data_dir / ".secret_key"
        if key_file.exists():
            cfg.secret_key = key_file.read_text().strip()
        else:
            cfg.secret_key = secrets.token_urlsafe(48)
            key_file.write_text(cfg.secret_key)
            key_file.chmod(0o600)
    return cfg
