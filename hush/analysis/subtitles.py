"""Subtitle parsing (SRT / WebVTT / ASS) and subtitle-based word timing.

Subtitles give cue-level timing only, so each word's time is estimated from its
character position inside the cue. Accuracy is lower than Whisper, so the
analyzer pads these detections more generously.
"""
from __future__ import annotations

import re

from .matcher import Word

_TS = r"(\d{1,2}):(\d{2}):(\d{2})[.,](\d{1,3})"
_SRT_LINE = re.compile(_TS + r"\s*-->\s*" + _TS)
_VTT_SHORT = re.compile(r"(?:(\d{1,2}):)?(\d{2}):(\d{2})\.(\d{3})\s*-->\s*(?:(\d{1,2}):)?(\d{2}):(\d{2})\.(\d{3})")
_TAGS = re.compile(r"<[^>]+>|\{[^}]*\}")


def _secs(h, m, s, ms) -> float:
    ms = (ms or "0").ljust(3, "0")[:3]
    return int(h or 0) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def clean_text(text: str) -> str:
    text = _TAGS.sub("", text).replace("\\N", " ").replace("\\n", " ")
    return re.sub(r"\s+", " ", text).strip()


def parse(text: str) -> list[dict]:
    """Return cues: [{start, end, text}] sorted by start."""
    text = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    if "[Events]" in text and "Dialogue:" in text:
        return _parse_ass(text)
    cues = []
    for block in re.split(r"\n\s*\n", text):
        lines = block.strip().split("\n")
        for i, line in enumerate(lines):
            m = _SRT_LINE.search(line)
            if m:
                g = m.groups()
                start, end = _secs(*g[0:4]), _secs(*g[4:8])
            else:
                m = _VTT_SHORT.search(line)
                if not m:
                    continue
                g = m.groups()
                start, end = _secs(*g[0:4]), _secs(*g[4:8])
            body = clean_text(" ".join(lines[i + 1:]))
            if body:
                cues.append({"start": start, "end": end, "text": body})
            break
    return sorted(cues, key=lambda c: c["start"])


def _parse_ass(text: str) -> list[dict]:
    cues, fmt = [], None
    for line in text.split("\n"):
        if line.startswith("Format:") and fmt is None and "Start" in line and "Text" in line:
            fmt = [f.strip() for f in line[7:].split(",")]
        elif line.startswith("Dialogue:") and fmt:
            parts = line[9:].split(",", len(fmt) - 1)
            row = dict(zip(fmt, (p.strip() for p in parts)))
            try:
                h, m, s = row["Start"].split(":")
                start = int(h) * 3600 + int(m) * 60 + float(s)
                h, m, s = row["End"].split(":")
                end = int(h) * 3600 + int(m) * 60 + float(s)
            except (KeyError, ValueError):
                continue
            body = clean_text(row.get("Text", ""))
            if body:
                cues.append({"start": start, "end": end, "text": body})
    return sorted(cues, key=lambda c: c["start"])


def cues_to_words(cues: list[dict]) -> list[Word]:
    """Estimate per-word timing by character position within each cue."""
    words: list[Word] = []
    for c in cues:
        text = re.sub(r"^\s*-\s*", "", c["text"])           # dialogue dashes
        text = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", text)    # [music], (laughs)
        tokens = [m for m in re.finditer(r"\S+", text)]
        if not tokens:
            continue
        total = len(text)
        dur = max(0.05, c["end"] - c["start"])
        for m in tokens:
            s = c["start"] + dur * (m.start() / total)
            e = c["start"] + dur * (m.end() / total)
            words.append(Word(m.group(), s, e))
    return words
