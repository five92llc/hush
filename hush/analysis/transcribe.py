"""Speech-to-text with word timestamps using faster-whisper.

faster-whisper is optional: if it isn't installed, Hush falls back to
subtitle-based detection. The model is downloaded once (to data/models) and
kept in memory between jobs.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from .matcher import Word

_model = None
_model_key = None
_lock = threading.Lock()


def available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def _load(cfg, models_dir: Path):
    global _model, _model_key
    from faster_whisper import WhisperModel

    key = (cfg.whisper_model, cfg.whisper_device, cfg.whisper_compute_type)
    with _lock:
        if _model is None or _model_key != key:
            device = cfg.whisper_device
            if device == "auto":
                try:
                    import ctranslate2
                    device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
                except Exception:  # noqa: BLE001
                    device = "cpu"
            compute = cfg.whisper_compute_type
            if device == "cuda" and compute == "int8":
                compute = "int8_float16"
            _model = WhisperModel(cfg.whisper_model, device=device, compute_type=compute,
                                  download_root=str(models_dir))
            _model_key = key
        return _model


def transcribe(wav_path: Path, cfg, models_dir: Path, duration: float | None,
               progress: Callable[[float], None], cancelled: Callable[[], bool]) -> list[Word]:
    model = _load(cfg, models_dir)
    segments, info = model.transcribe(
        str(wav_path),
        language=cfg.language or None,
        word_timestamps=True,
        vad_filter=True,                       # skip silence and pure music
        vad_parameters={"min_silence_duration_ms": 500},
        condition_on_previous_text=False,      # reduces runaway hallucinations
        beam_size=5,
    )
    total = duration or getattr(info, "duration", None) or 1.0
    words: list[Word] = []
    for seg in segments:
        if cancelled():
            raise InterruptedError("cancelled")
        for w in seg.words or []:
            words.append(Word(w.word, float(w.start), float(w.end)))
        progress(min(0.99, seg.end / total))
    return words
