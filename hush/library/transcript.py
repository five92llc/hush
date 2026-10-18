"""Turn a scan's timed words into a readable transcript (TXT, SRT or WebVTT)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..analysis.matcher import Word


def load_words(cache_dir: Path, key: str) -> tuple[str, list[Word]] | None:
    f = cache_dir / f"{key}.words.json"
    if not f.is_file():
        return None
    data = json.loads(f.read_text())
    return data["engine"], [Word(*w) for w in data["words"]]


def mask(words: list[Word], detections: list[dict]) -> list[Word]:
    """Replace the letters after the first one in every word the filter caught: f***."""
    out = []
    for w in words:
        if any(d["start"] - 0.02 <= w.start and w.end <= d["end"] + 0.02 for d in detections):
            core = w.text.strip()
            lead = w.text[:len(w.text) - len(w.text.lstrip())]
            masked = core[:1] + re.sub(r"[A-Za-z0-9]", "*", core[1:]) if len(core) > 1 else "*"
            out.append(Word(lead + masked, w.start, w.end))
        else:
            out.append(w)
    return out


def cues(words: list[Word], max_words: int = 11, max_gap: float = 0.9, max_len: float = 6.5) -> list[tuple[float, float, str]]:
    out: list[tuple[float, float, str]] = []
    cur: list[Word] = []
    for w in words:
        if cur and (len(cur) >= max_words or w.start - cur[-1].end > max_gap or w.end - cur[0].start > max_len
                    or re.search(r"[.!?]$", cur[-1].text.strip()) and len(cur) >= 4):
            out.append(_cue(cur))
            cur = []
        cur.append(w)
    if cur:
        out.append(_cue(cur))
    return out


def _cue(ws: list[Word]) -> tuple[float, float, str]:
    return ws[0].start, ws[-1].end, " ".join(w.text.strip() for w in ws if w.text.strip())


def _ts(t: float, sep: str) -> str:
    ms = int(round(max(0.0, t) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def to_srt(words: list[Word]) -> str:
    return "".join(f"{i}\n{_ts(a, ',')} --> {_ts(b, ',')}\n{t}\n\n" for i, (a, b, t) in enumerate(cues(words), 1))


def to_vtt(words: list[Word]) -> str:
    return "WEBVTT\n\n" + "".join(f"{_ts(a, '.')} --> {_ts(b, '.')}\n{t}\n\n" for a, b, t in cues(words))


def to_txt(words: list[Word], title: str = "") -> str:
    """Running text; a new paragraph after a pause of two seconds or more."""
    paras: list[list[str]] = [[]]
    last = None
    for w in words:
        if last is not None and w.start - last > 2.0 and paras[-1]:
            paras.append([])
        if w.text.strip():
            paras[-1].append(w.text.strip())
        last = w.end
    body = "\n\n".join(" ".join(p) for p in paras if p)
    return (f"{title}\n{'=' * len(title)}\n\n" if title else "") + body + "\n"
