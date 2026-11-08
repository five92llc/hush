"""Intros and credits of TV episodes, so the player can offer "Skip intro", "Skip credits" and start the next episode by itself.

Where the marks come from, best first:
  manual   set by hand in the player (for one episode or the whole season)
  chapter  chapters in the file called "Intro", "Opening", "Credits", "Ending" ...
  detected the same sound found in neighbouring episodes of a season (the theme tune, the end music), by comparing audio
           fingerprints (ffmpeg's chromaprint). Needs numpy; episodes are compared in pairs, so a season needs two or more.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import re
import subprocess
import threading
import time
from pathlib import Path

from . import media
from .sources import media_key

log = logging.getLogger("hush.segments")

ITEM = 1365 / 11025                  # seconds of sound in one chromaprint value
INTRO_REGION = 600                   # the first ten minutes are searched for the intro
CREDITS_REGION = 420                 # the last seven minutes for the credits
LIMITS = {"intro": (10, 180), "credits": (12, 400)}       # shortest and longest believable lengths, seconds
INTRO_RE = re.compile(r"\b(intro|opening|op|title sequence|main titles?|theme)\b", re.I)
CREDITS_RE = re.compile(r"\b(credits?|ending|end|outro|ed)\b", re.I)
KINDS = ("intro", "credits")


def chapter_segments(chapters: list[dict], duration: float | None) -> dict[str, tuple[float, float]]:
    """Intro and credits from chapter titles: {"intro": (start, end), "credits": (start, end)}."""
    out: dict[str, tuple[float, float]] = {}
    for c in chapters:
        title = (c.get("tags") or {}).get("title", "")
        try:
            start, end = float(c["start_time"]), float(c["end_time"])
        except (KeyError, ValueError):
            continue
        if end - start < 5:
            continue
        if "intro" not in out and INTRO_RE.search(title) and not re.search(r"credit|ending|end", title, re.I) and start < (duration or 1e9) * 0.4:
            out["intro"] = (start, end)
        elif "credits" not in out and CREDITS_RE.search(title) and start > (duration or 0) * 0.5:
            out["credits"] = (start, duration or end) if end >= (duration or 0) - 30 else (start, end)
    return out


def best_alignment(a, b, max_shift: int = 1000, min_items: int = 100):
    """Where two fingerprints share a stretch of sound: (start in a, start in b, items) or None.

    Every shift of b against a is tried; the one where the most values agree (few differing bits) is kept, and its longest
    unbroken run is returned.
    """
    import numpy as np
    lut = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)
    best, best_count = None, 0
    for s in range(-max_shift, max_shift + 1):
        a0 = max(0, -s); b0 = a0 + s
        n = min(len(a) - a0, len(b) - b0)
        if n < min_items:
            continue
        x = np.bitwise_xor(a[a0:a0 + n], b[b0:b0 + n])
        good = lut[x.view(np.uint8)].reshape(-1, 4).sum(axis=1) <= 9
        count = int(good.sum())
        if count > best_count:
            best, best_count = (s, a0, b0, n, good), count
    if not best or best_count < min_items:
        return None
    s, a0, b0, n, good = best
    # the longest run, bridging gaps of up to three values (a noisy moment inside the tune)
    run_start, run_len, gap, top = None, 0, 0, (0, 0)
    for i, g in enumerate(good):
        if g:
            if run_start is None:
                run_start, run_len = i, 0
            run_len = i - run_start + 1; gap = 0
            if run_len > top[1]:
                top = (run_start, run_len)
        elif run_start is not None:
            gap += 1
            if gap > 3:
                run_start = None
    start, length = top
    if length < min_items:
        return None
    return a0 + start, b0 + start, length


def _quietly():
    """Run below everything else: finding intros must never slow down someone watching."""
    try:
        os.nice(10)
    except (AttributeError, OSError):
        pass


class SegmentFinder:
    def __init__(self, cfg, db, registry, probe_fn):
        self.cfg, self.db, self.registry, self.probe_fn = cfg, db, registry, probe_fn
        self.dir = cfg.cache_dir / "fingerprints"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.q: queue.Queue[tuple[str, int]] = queue.Queue()
        self.pending: set[tuple[str, int]] = set()
        self.current = ""
        self.done_seasons = 0
        self._lock = threading.Lock()
        threading.Thread(target=self._worker, name="segments", daemon=True).start()

    # ---- what is known ---------------------------------------------------------------------------------------
    def marks(self, key: str) -> dict:
        return {r["kind"]: {"start": r["start"], "end": r["end"], "source": r["source"]} for r in self.db.get_segments(key)}

    def status(self) -> dict:
        return {"queued": self.q.qsize(), "running": self.current, "done": self.done_seasons, "numpy": self._numpy()}

    @staticmethod
    def _numpy() -> bool:
        try:
            import numpy  # noqa: F401
            return True
        except ImportError:
            return False

    # ---- queueing ------------------------------------------------------------------------------------------------
    def queue_season(self, show_key: str, season: int, force: bool = False) -> bool:
        k = (show_key, season)
        eps = [e for e in self.db.episodes_of(show_key) if e.get("season") == season]
        if len(eps) < 2 and not force:
            return False
        if not force and (self.db.get_segment_scan(f"{show_key}:{season}") or {}).get("episodes") == len(eps):
            return False
        with self._lock:
            if k in self.pending:
                return False
            self.pending.add(k)
        self.q.put(k)
        return True

    def queue_all(self) -> int:
        n = 0
        for s in self.db.list_shows():
            for season in sorted({e["season"] for e in self.db.episodes_of(s["show_key"]) if e.get("season") is not None}):
                n += self.queue_season(s["show_key"], season)
        return n

    def _worker(self) -> None:
        while True:
            k = self.q.get()
            self.current = f"{k[0]} season {k[1]}"
            try:
                self.scan_season(*k)
                self.done_seasons += 1
            except Exception:
                log.exception("intro and credits scan of %s failed", k)
            finally:
                with self._lock:
                    self.pending.discard(k)
                self.current = ""

    # ---- the scan -------------------------------------------------------------------------------------------------------
    def _ffprobe_chapters(self, src: str, item: str) -> list[dict]:
        try:
            ref = self.registry.get(src).resolve(item)
            cmd = [self.cfg.ffprobe, "-v", "error", "-print_format", "json", "-show_chapters", *media.ffmpeg_input(ref, src, item)]
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout
            return json.loads(out or "{}").get("chapters", [])
        except (OSError, subprocess.SubprocessError, ValueError, KeyError):
            return []

    def _fingerprint(self, src: str, item: str, kind: str, duration: float):
        """The chromaprint of the start (intro) or the end (credits) of an episode: (values, seconds at which they start)."""
        import numpy as np
        f = self.dir / f"{media_key(src, item)}.{kind}.npz"
        if f.exists():
            z = np.load(f)
            return z["fp"], float(z["offset"])
        offset = 0.0 if kind == "intro" else max(0.0, duration - CREDITS_REGION)
        length = INTRO_REGION if kind == "intro" else CREDITS_REGION
        ref = self.registry.get(src).resolve(item)
        cmd = [self.cfg.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-threads", "2", "-ss", f"{offset:.2f}", *media.ffmpeg_input(ref, src, item),
               "-t", str(length), "-vn", "-sn", "-ac", "1", "-ar", "11025", "-f", "chromaprint", "-fp_format", "raw", "pipe:1"]
        raw = subprocess.run(cmd, capture_output=True, timeout=600, preexec_fn=_quietly).stdout
        fp = np.frombuffer(raw, dtype="<u4").copy()
        if len(fp) < 200:
            return None
        np.savez(f, fp=fp, offset=offset)
        return fp, offset

    def scan_season(self, show_key: str, season: int) -> dict:
        eps = [e for e in self.db.episodes_of(show_key) if e.get("season") == season]
        found: dict[str, dict] = {}                                       # media_key -> kind -> (start, end, source)
        durations: dict[str, float] = {}
        for e in eps:
            key = e["media_key"]
            try:
                durations[key] = float(self.probe_fn(e["source_id"], e["item_id"]).duration or 0)
            except Exception:
                durations[key] = 0.0
            ch = chapter_segments(self._ffprobe_chapters(e["source_id"], e["item_id"]), durations[key])
            for kind, (a, b) in ch.items():
                found.setdefault(key, {})[kind] = (a, b, "chapter")
        if self._numpy() and len(eps) >= 2:
            for kind in KINDS:
                fps = {}
                for e in eps:
                    try:
                        fp = self._fingerprint(e["source_id"], e["item_id"], kind, durations.get(e["media_key"], 0))
                    except (OSError, subprocess.SubprocessError, ValueError):
                        fp = None
                    if fp:
                        fps[e["media_key"]] = fp
                order = [e["media_key"] for e in eps if e["media_key"] in fps]
                lo, hi = LIMITS[kind]
                for i in range(len(order) - 1):
                    ka, kb = order[i], order[i + 1]
                    (fa, oa), (fb, ob) = fps[ka], fps[kb]
                    m = best_alignment(fa, fb, min_items=int(lo / ITEM))
                    if not m:
                        continue
                    ia, ib, n = m
                    if not (lo <= n * ITEM <= hi):
                        continue
                    for key, idx, off in ((ka, ia, oa), (kb, ib, ob)):
                        if kind in found.get(key, {}):
                            continue
                        start = off + idx * ITEM
                        end = start + n * ITEM
                        if kind == "credits" and durations.get(key) and end > durations[key] - 45:
                            end = durations[key]                         # the credits run to the end of the file
                        found.setdefault(key, {})[kind] = (round(start, 2), round(end, 2), "detected")
        saved = 0
        for key, kinds in found.items():
            have = {r["kind"]: r["source"] for r in self.db.get_segments(key)}
            for kind, (a, b, source) in kinds.items():
                if have.get(kind) == "manual" or (have.get(kind) == "chapter" and source == "detected"):
                    continue
                self.db.set_segment(key, kind, a, b, source)
                saved += 1
        self.db.set_segment_scan(f"{show_key}:{season}", len(eps))
        log.info("intros and credits: %s season %s: %d marks", show_key, season, saved)
        return {"episodes": len(eps), "marks": saved}
