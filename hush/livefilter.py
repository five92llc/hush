"""Language filter for live TV, driven by the captions in the stream.

How it works. A channel is pulled by one ffmpeg that copies it into short raw segments. Every new segment is looked at
for closed captions (CEA-608/708, carried inside the video); the captions are matched against the word list the same way
subtitles are for a movie, and the flagged words become mute windows. Each raw segment is then published DELAY seconds
after it arrived, with its audio silenced in those windows (only segments that need it are re-encoded, the video is always
copied). The delay is what gives the filter time to hear a word before the viewer does.

Captions only say roughly when a word was spoken (live captions run a second or two behind the speech), so the windows are
wider than a word: a short silence around the flagged word rather than a precise bleep.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

from .analysis import subtitles
from .analysis.matcher import Word, build_ranges, normalize

log = logging.getLogger("hush.livefilter")

DELAY = 10.0                 # seconds the viewer is behind the broadcast
PAD_BEFORE, PAD_AFTER, MERGE_GAP = 2.2, 0.7, 1.0     # measured on a real channel: a caption word is estimated 1-1.7 s after it was spoken
STRICT_GIVE_UP = 45.0        # a kids session waits this long for the first caption before refusing
KEEP_CUES = 120.0
WINDOW = 6                   # segments in the published playlist
KEEP_OUT = 14
IDLE_SECONDS = 120
GRACE_SECONDS = 20           # a session nobody watches any more lingers this long (flipping back to a channel is instant)
MAX_SESSIONS = 4
NAME = re.compile(r"^[A-Za-z0-9_.-]+\.(m3u8|ts|mp4)$")
CC_PROBE_SECONDS = 8.0       # no captions seen by then: try speech recognition instead
ASR_PAD_BEFORE, ASR_PAD_AFTER, ASR_MERGE_GAP = 0.4, 0.5, 0.4   # recognised words carry real timings, so the windows can be tight
ASR_WINDOW_SEGMENTS, ASR_STEP_SEGMENTS = 4, 2
ASR_EDGE_LEFT, ASR_EDGE_RIGHT = 0.6, 0.5                       # words cut by the edge of a window are not trusted
PLAYER_LATENCY = 4.0         # roughly how long a player holds a published segment before showing it: captions are shown this much later
CAPTION_WORDS = 9            # a caption line is at most this many words
ASR_ADULT_WAIT = 8.0         # an adult profile waits this long past the delay for recognition before the audio goes out unfiltered


class LiveFilterError(Exception):
    pass


def mute_expression(windows: list[tuple[float, float]]) -> str:
    """The ffmpeg audio filter that silences these (start, end) windows."""
    parts = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in windows)
    return f"volume=enable='{parts}':volume=0"


def parse_playlist(text: str) -> list[tuple[str, float]]:
    """[(segment name, duration)] from an HLS playlist."""
    out, dur = [], None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#EXTINF:"):
            try:
                dur = float(line[8:].split(",")[0])
            except ValueError:
                dur = None
        elif line and not line.startswith("#") and dur is not None:
            out.append((line, dur))
            dur = None
    return out


class LiveASR:
    """Speech recognition for live channels: one small model shared by every session, one window at a time."""

    def __init__(self, cfg, models_dir: Path):
        self.cfg, self.models_dir = cfg, models_dir
        self._model = None
        self._lock = threading.Lock()          # one window at a time keeps CPU use predictable
        self.active = 0                        # sessions currently using recognition
        self._slots = threading.Lock()

    def available(self) -> bool:
        from .analysis import transcribe
        return transcribe.available()

    def claim(self) -> bool:
        with self._slots:
            if self.active >= max(1, self.cfg.analysis.live_asr_sessions):
                return False
            self.active += 1
            return True

    def release(self) -> None:
        with self._slots:
            self.active = max(0, self.active - 1)

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            a = self.cfg.analysis
            device = a.whisper_device
            if device == "auto":
                try:
                    import ctranslate2
                    device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
                except Exception:  # noqa: BLE001
                    device = "cpu"
            compute = "int8_float16" if device == "cuda" else a.whisper_compute_type
            self._model = WhisperModel(a.live_whisper_model, device=device, compute_type=compute,
                                       cpu_threads=max(1, a.live_whisper_threads), download_root=str(self.models_dir))
        return self._model

    def words(self, wav: Path) -> list[Word]:
        """Words (with times in seconds from the start of the file) in a 16 kHz mono recording."""
        with self._lock:
            model = self._load()
            segments, _ = model.transcribe(str(wav), language=self.cfg.analysis.language or None, word_timestamps=True, beam_size=1,
                                           vad_filter=True, vad_parameters={"min_silence_duration_ms": 300},
                                           condition_on_previous_text=False, temperature=0.0)
            return [Word(w.word, float(w.start), float(w.end)) for seg in segments for w in (seg.words or [])]


class Session:
    def __init__(self, live: "LiveFilter", key: str, folder: Path, input_args: list[str], cats: set[str] | None, strict: bool):
        self.live, self.key, self.folder, self.strict, self.cats = live, key, folder, strict, cats
        self.sid = folder.name
        self.raw, self.out = folder / "raw", folder / "out"
        self.raw.mkdir(parents=True); self.out.mkdir()
        self.input_args = input_args
        self.owners: set[str] = set()
        self.last = time.time()
        self.empty_since: float | None = None
        self.started = time.time()
        self.state = "starting"          # starting | live | nocaptions | failed | stopped
        self.error = ""
        self.cues: list[dict] = []
        self.cue_keys: set[tuple] = set()
        self.cues_seen = False
        self.ranges: list[dict] = []
        self.segments: list[dict] = []   # raw segments, in order: seq, name, dur, t0, ready, extracted
        self.published: list[dict] = []  # out segments in the playlist window
        self.next_pub = 0
        self.last_pub = 0.0
        self.muted = 0
        self.mode = "pending"            # pending | captions | asr | none
        self.words: list[Word] = []      # recognised words (asr mode), times since the first segment
        self.covered_until = 0.0         # stream time up to which the words are known (asr mode)
        self.asr_end = -1                # index of the last segment included in a recognised window
        self.asr_claimed = False
        self.behind = False
        self.caption_log: list[dict] = []   # what the screen should show, line by line: id, start/end (stream time), text, show_at (wall clock)
        self.caption_seq = 0
        self.caption_tail: list[str] = []   # the last words shown, so a roll-up caption that repeats them is not shown twice
        self.proc: subprocess.Popen | None = None
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.mp4_clients = 0

    # ---- starting ---------------------------------------------------------------
    def start(self) -> None:
        cfg = self.live.cfg
        cmd = [cfg.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin"]
        if self.live.realtime_inputs:
            cmd += ["-re"]
        cmd += ["-fflags", "+genpts+discardcorrupt", *self.input_args,
                "-map", "0:v:0", "-map", "0:a:0?", "-c", "copy", "-f", "hls", "-hls_time", "2", "-hls_list_size", "40",
                "-hls_flags", "delete_segments+independent_segments+omit_endlist",
                "-hls_segment_filename", str(self.raw / "s%06d.ts"), str(self.raw / "index.m3u8")]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=open(self.folder / "ingest.log", "wb"))
        for target, name in ((self._watch_raw, "raw"), (self._publish_loop, "publish"), (self._asr_loop, "asr")):
            threading.Thread(target=target, name=f"livefilter-{name}-{self.sid}", daemon=True).start()

    # ---- watching the incoming segments ------------------------------------------
    def _watch_raw(self) -> None:
        seen = 0
        t0 = 0.0
        while not self.stop_event.is_set():
            try:
                entries = parse_playlist((self.raw / "index.m3u8").read_text(errors="ignore"))
            except OSError:
                entries = []
            if self.proc and self.proc.poll() is not None and not entries and self.state == "starting":
                tail = (self.folder / "ingest.log").read_text(errors="ignore")[-300:].strip()
                self._fail(f"The channel did not answer: {tail or 'unknown error'}")
                return
            names = [s["name"] for s in self.segments]
            for name, dur in entries:
                if name in names:
                    continue
                seg = {"seq": len(self.segments), "name": name, "dur": dur, "t0": t0, "ready": time.time(), "extracted": False}
                t0 += dur
                with self.lock:
                    self.segments.append(seg)
                try:
                    self._extract(seg)
                except Exception as exc:  # noqa: BLE001 - a failed caption read must not stop the stream
                    log.warning("captions for %s: %s", name, exc)
                seg["extracted"] = True
            self._decide_mode()
            time.sleep(0.4)

    def _decide_mode(self) -> None:
        """Captions if the stream has them; otherwise speech recognition, when the machine has room for it."""
        chan = self.key.split("|")[0]
        if self.mode == "pending":
            if self.cues_seen:
                self.mode = "captions"
                self.live.no_captions.discard(chan)
            elif self.segments and (chan in self.live.no_captions or time.time() - self.started > CC_PROBE_SECONDS):
                if self.live.asr.available() and self.live.asr.claim():
                    self.asr_claimed = True
                    self.mode = "asr"
                    self.live.no_captions.add(chan)
                else:
                    self.mode = "none"
                    self.state = "nocaptions"
                    self.error = "This channel has no captions and speech recognition is not available, so it cannot be filtered."
        elif self.mode == "captions" and not self.cues_seen:
            pass
        if self.mode == "asr":
            self.state = "live" if self.state != "failed" else self.state

    # ---- speech recognition (channels without captions) -------------------------------
    def _asr_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                if self.mode != "asr" or not self._asr_step():
                    time.sleep(0.3)
            except Exception as exc:  # noqa: BLE001 - recognition trouble must not end the stream; the publish gate keeps it safe
                log.warning("recognition: %s", exc)
                time.sleep(1.0)

    def _asr_step(self) -> bool:
        """Recognise the newest window once two new segments have arrived. Returns True when it did work."""
        with self.lock:
            n = len(self.segments)
            segs = list(self.segments[max(0, n - ASR_WINDOW_SEGMENTS):n])
        if not segs or (n - 1) - self.asr_end < (ASR_STEP_SEGMENTS if self.asr_end >= 0 else 1) or any(not (self.raw / g["name"]).exists() for g in segs):
            return False
        base, end = segs[0]["t0"], segs[-1]["t0"] + segs[-1]["dur"]
        tmp = self.folder / "asr.ts"
        wav = self.folder / "asr.wav"
        with open(tmp, "wb") as out:
            for g in segs:
                out.write((self.raw / g["name"]).read_bytes())
        r = subprocess.run([self.live.cfg.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(tmp), "-vn", "-ac", "1",
                            "-ar", "16000", str(wav)], capture_output=True, timeout=30)
        if r.returncode != 0 or not wav.exists():
            self.asr_end = n - 1
            return True
        words = self.live.asr.words(wav)
        left = base if self.asr_end < 0 else base + ASR_EDGE_LEFT           # the very first window has no earlier window to defer to
        right = end - ASR_EDGE_RIGHT
        self.add_words([Word(w.text, base + w.start, base + w.end) for w in words if left <= base + w.start and base + w.end <= right])
        self.covered_until = right
        self.asr_end = n - 1
        for g in segs:
            g["extracted"] = True
        return True

    def add_words(self, words: list[Word]) -> None:
        """Take recognised words (times since the first segment) and refresh the mute windows."""
        known = [(normalize(w.text), w.start) for w in self.words]
        new: list[Word] = []
        for w in words:
            n = normalize(w.text)
            if n and not any(n == k and abs(w.start - t) < 0.4 for k, t in known):
                self.words.append(w)
                new.append(w)
        self._caption_words(sorted(new, key=lambda w: w.start))
        self.words.sort(key=lambda w: w.start)
        if self.words:
            horizon = self.words[-1].end - KEEP_CUES
            self.words = [w for w in self.words if w.end >= horizon]
        det = self.live.wordlist.find(self.words)
        if self.cats is not None:
            det = [d for d in det if d["category"] in self.cats]
        self.ranges = build_ranges(det, ASR_PAD_BEFORE, ASR_PAD_AFTER, ASR_MERGE_GAP)

    # ---- captions for the screen ---------------------------------------------------
    def _wall_for(self, t: float) -> float:
        """When (wall clock) the broadcast reached stream time t, judged from when each segment arrived."""
        segs = self.segments
        if not segs:
            return time.time()
        for s in segs:
            if s["t0"] <= t < s["t0"] + s["dur"]:
                return s["ready"] - (s["t0"] + s["dur"] - t)
        last = segs[-1]
        return last["ready"] + (t - (last["t0"] + last["dur"])) if t >= last["t0"] else segs[0]["ready"] - (segs[0]["t0"] - t)

    def _caption_words(self, words: list[Word]) -> None:
        """Group recognised words into caption lines: a pause, or nine words, ends a line."""
        line: list[Word] = []
        for w in words + [None]:
            if line and (w is None or w.start - line[-1].end > 0.9 or len(line) >= CAPTION_WORDS):
                self._caption(line[0].start, line[-1].end, " ".join(x.text.strip() for x in line))
                line = []
            if w is not None:
                line.append(w)

    def _caption(self, start: float, end: float, text: str) -> None:
        """Add a caption. Words that repeat the end of the previous one (live captions roll up) are not shown again."""
        words = text.split()
        norm = [normalize(w) for w in words]
        k = 0
        for n in range(min(len(self.caption_tail), len(norm)), 0, -1):          # the longest end of what was shown that begins this one
            if self.caption_tail[-n:] == norm[:n]:
                k = n
                break
        words, norm = words[k:], norm[k:]
        if not words:
            return
        self.caption_tail = (self.caption_tail + norm)[-40:]
        span = max(0.4, end - start)
        for i in range(0, len(words), CAPTION_WORDS):
            chunk = words[i:i + CAPTION_WORDS]
            a = start + span * i / len(words)
            b = start + span * min(len(words), i + CAPTION_WORDS) / len(words)
            self.caption_seq += 1
            self.caption_log.append({"id": self.caption_seq, "start": a, "end": b, "text": " ".join(chunk),
                                     "show_at": self._wall_for(a) + DELAY + PLAYER_LATENCY})
        self.caption_log = self.caption_log[-300:]

    def captions_after(self, after: int) -> dict:
        now = time.time()
        cues = [{"id": c["id"], "show_in": round(max(0.0, c["show_at"] - now), 2), "dur": round(max(1.8, min(6.0, c["end"] - c["start"] + 0.8)), 2),
                 "text": c["text"]} for c in self.caption_log if c["id"] > after]
        return {"cues": cues, "next": self.caption_seq, "mode": self.mode}

    def _extract(self, seg: dict) -> None:
        """Read the captions of this segment (with the one before it, so a caption that began earlier is whole)."""
        prev = self.segments[seg["seq"] - 1] if seg["seq"] > 0 else None
        files = [p for p in ([prev] if prev else []) + [seg] if (self.raw / p["name"]).exists()]
        if not files:
            return
        tmp = self.folder / "cc.ts"
        with open(tmp, "wb") as out:
            for p in files:
                out.write((self.raw / p["name"]).read_bytes())
        base = files[0]["t0"]
        res = subprocess.run([self.live.cfg.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-f", "lavfi", "-i",
                              f"movie={tmp}[out0+subcc]", "-map", "0:s:0", "-f", "srt", "-"], capture_output=True, timeout=25)
        cues = subtitles.parse(res.stdout.decode("utf-8", "replace"))
        self.add_cues([{"start": base + c["start"], "end": base + c["end"], "text": c["text"]} for c in cues])

    def add_cues(self, cues: list[dict]) -> None:
        """Take new caption cues (times in seconds since the first segment) and refresh the mute windows."""
        fresh = False
        for c in cues:
            k = (round(c["start"], 1), c["text"])
            if k in self.cue_keys:
                continue
            self.cue_keys.add(k)
            self.cues.append(c)
            fresh = True
        if not fresh:
            return
        self.cues_seen = True
        if self.mode in ("pending", "captions"):
            for c in sorted(cues, key=lambda c: c["start"]):
                self._caption(c["start"], c["end"], c["text"])
        if self.state == "nocaptions":
            self.state = "live"
        horizon = max(c["end"] for c in self.cues) - KEEP_CUES
        self.cues = [c for c in self.cues if c["end"] >= horizon]
        det = self.live.wordlist.find(subtitles.cues_to_words(sorted(self.cues, key=lambda c: c["start"])))
        if self.cats is not None:
            det = [d for d in det if d["category"] in self.cats]
        self.ranges = build_ranges(det, PAD_BEFORE, PAD_AFTER, MERGE_GAP)

    # ---- publishing, delayed and muted -----------------------------------------------
    def _publish_loop(self) -> None:
        while not self.stop_event.is_set():
            with self.lock:
                if not self.published and self.mode != "pending":   # the source hands over a backlog at the start: begin near its newest part
                    now = time.time()
                    eligible = [i for i, s in enumerate(self.segments) if now >= s["ready"] + DELAY]
                    if eligible and eligible[-1] - self.next_pub > 2:
                        self.next_pub = eligible[-1] - 2
                seg = self.segments[self.next_pub] if self.next_pub < len(self.segments) else None
                following = self.segments[self.next_pub + 1] if self.next_pub + 1 < len(self.segments) else None
            now = time.time()
            if seg is None or now < seg["ready"] + DELAY:
                time.sleep(0.2)
                continue
            if self.published and now < self.last_pub + 0.8 * self.published[-1]["dur"]:
                time.sleep(0.1)                              # one segment per segment-length, so a burst from the source never outruns the player
                continue
            age = now - (seg["ready"] + DELAY)               # how long this segment has been ready to go out
            if self.mode == "pending":
                if self.strict and now - self.started > STRICT_GIVE_UP:
                    self._refuse("This channel has no captions, so it cannot be filtered.")
                    return
                time.sleep(0.3)
                continue
            if self.mode == "none" and self.strict:
                self._refuse(self.error or "This channel cannot be filtered.")
                return
            if self.mode == "captions" and following is not None and not following["extracted"] and age < 3:
                time.sleep(0.2)                              # a moment for the next segment's captions to land
                continue
            if self.mode == "asr" and self.covered_until < seg["t0"] + seg["dur"]:
                if self.strict:                              # a kids profile never hears audio that was not checked
                    if age > STRICT_GIVE_UP:
                        self._refuse("The language filter could not keep up on this channel.")
                        return
                    time.sleep(0.2)
                    continue
                if age < ASR_ADULT_WAIT:
                    time.sleep(0.2)
                    continue
                self.behind = True
            try:
                self._publish(seg)
            except Exception as exc:  # noqa: BLE001
                log.warning("publishing %s failed: %s", seg["name"], exc)
                self.next_pub += 1
                continue
            self.next_pub += 1
            if self.state == "starting":
                self.state = "live"

    def _refuse(self, message: str) -> None:
        self.state, self.error = "nocaptions", message
        self.stop_event.set()

    def windows_for(self, seg: dict) -> list[tuple[float, float]]:
        lo, hi = seg["t0"], seg["t0"] + seg["dur"]
        return [(max(r["start"], lo) - lo, min(r["end"], hi) - lo) for r in self.ranges if r["end"] > lo and r["start"] < hi]

    def _publish(self, seg: dict) -> None:
        src, dst = self.raw / seg["name"], self.out / seg["name"]
        if not src.exists():
            return
        windows = self.windows_for(seg)
        if not windows:
            shutil.copyfile(src, dst)
        else:
            self._mute_copy(src, dst, windows)
            self.muted += 1
        self.last_pub = time.time()
        self.published.append({"name": seg["name"], "dur": seg["dur"], "seq": seg["seq"]})
        for old in self.published[:-KEEP_OUT]:
            (self.out / old["name"]).unlink(missing_ok=True)
        self.published = self.published[-KEEP_OUT:]
        self._write_playlist()

    def _mute_copy(self, src: Path, dst: Path, windows: list[tuple[float, float]]) -> None:
        cfg = self.live.cfg
        probe = subprocess.run([cfg.ffprobe, "-v", "error", "-show_entries", "format=start_time", "-of", "csv=p=0", str(src)],
                               capture_output=True, text=True, timeout=15)
        try:
            pts0 = float(probe.stdout.strip())
        except ValueError:
            pts0 = 0.0
        absolute = [(a + pts0, b + pts0) for a, b in windows]                # -copyts keeps the segment's own clock, so continuity holds
        cmd = [cfg.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-copyts", "-i", str(src),
               "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "copy", "-af", mute_expression(absolute), "-c:a", "aac", "-b:a", "128k",
               "-muxdelay", "0", "-muxpreload", "0", "-f", "mpegts", str(dst)]
        r = subprocess.run(cmd, capture_output=True, timeout=30)
        if r.returncode != 0 or not dst.exists():
            raise LiveFilterError(r.stderr.decode(errors="ignore")[-200:])

    def _write_playlist(self) -> None:
        win = self.published[-WINDOW:]
        lines = ["#EXTM3U", "#EXT-X-VERSION:3", f"#EXT-X-TARGETDURATION:{int(max(s['dur'] for s in win)) + 1}",
                 f"#EXT-X-MEDIA-SEQUENCE:{win[0]['seq']}"]
        for s in win:
            lines += [f"#EXTINF:{s['dur']:.3f},", s["name"]]
        tmp = self.out / "index.m3u8.tmp"
        tmp.write_text("\n".join(lines) + "\n")
        tmp.replace(self.out / "index.m3u8")

    # ---- state ---------------------------------------------------------------------------
    def _fail(self, message: str) -> None:
        self.state, self.error = "failed", message
        self.stop_event.set()

    def status(self) -> dict:
        return {"state": self.state, "mode": self.mode, "captions": self.cues_seen, "cues": len(self.cues), "words": len(self.words),
                "muted": self.muted, "delay": DELAY, "error": self.error, "behind": self.behind, "ready": len(self.published) >= 2}

    def stop(self) -> None:
        self.state = "stopped" if self.state not in ("failed", "nocaptions") else self.state
        self.stop_event.set()
        if self.asr_claimed:
            self.asr_claimed = False
            self.live.asr.release()
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        shutil.rmtree(self.folder, ignore_errors=True)


class LiveFilter:
    def __init__(self, cfg, wordlist, root: Path, realtime_inputs: bool = False, asr=None):
        self.cfg, self.wordlist, self.root = cfg, wordlist, root
        self.asr = asr or LiveASR(cfg, cfg.data_dir / "models")
        self.no_captions: set[str] = set()            # channels already seen to have none: next time recognition starts straight away
        self.realtime_inputs = realtime_inputs        # tests feed a file; a real channel is already live
        shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        self.sessions: dict[str, Session] = {}
        self._lock = threading.Lock()
        threading.Thread(target=self._reap, name="livefilter-reaper", daemon=True).start()

    def open(self, key: str, input_args: list[str], cats: set[str] | None, owner: str, strict: bool, timeout: float = 70.0) -> Session:
        """Join (or start) the filtered feed of a channel and wait until it can be played."""
        full = f"{key}|{','.join(sorted(cats)) if cats is not None else '*'}|{int(strict)}"
        with self._lock:
            for s in [s for s in self.sessions.values() if owner and owner in s.owners and s.key != full]:
                self._release(s, owner)                        # this tab moved on to another channel
            sess = self.sessions.get(full)
            if sess is None or sess.state in ("failed", "stopped") or sess.stop_event.is_set():
                if sess:
                    self._drop(sess)
                while len(self.sessions) >= MAX_SESSIONS:
                    self._drop(min(self.sessions.values(), key=lambda s: s.last))
                sess = Session(self, full, self.root / uuid.uuid4().hex[:12], input_args, cats, strict)
                self.sessions[full] = sess
                sess.start()
            sess.owners.add(owner or uuid.uuid4().hex)
            sess.empty_since = None
        end = time.time() + timeout
        while time.time() < end:
            if sess.status()["ready"]:
                return sess
            if sess.state in ("failed", "nocaptions") and sess.stop_event.is_set():
                raise LiveFilterError(sess.error or "The channel could not be filtered")
            time.sleep(0.3)
        raise LiveFilterError("The channel did not start in time")

    def release(self, owner: str) -> None:
        with self._lock:
            for s in list(self.sessions.values()):
                if owner in s.owners:
                    self._release(s, owner)

    def _release(self, s: Session, owner: str) -> None:
        s.owners.discard(owner)
        if not s.owners:
            s.empty_since = time.time()

    def get(self, sid: str) -> Session | None:
        with self._lock:
            return next((s for s in self.sessions.values() if s.sid == sid), None)

    def file(self, sid: str, name: str) -> Path | None:
        if not NAME.match(name):
            return None
        s = self.get(sid)
        if not s:
            return None
        s.last = time.time()
        p = s.out / name
        return p if p.is_file() else None

    def _drop(self, s: Session) -> None:
        self.sessions.pop(s.key, None)
        s.stop()

    def stop_all(self) -> None:
        with self._lock:
            for s in list(self.sessions.values()):
                self._drop(s)

    def _reap(self) -> None:
        while True:
            time.sleep(5)
            with self._lock:
                now = time.time()
                for s in list(self.sessions.values()):
                    if (s.empty_since and now - s.empty_since > GRACE_SECONDS) or now - s.last > IDLE_SECONDS:
                        self._drop(s)
