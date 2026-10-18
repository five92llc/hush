"""Background analysis jobs: media -> timed words -> mute ranges."""
from __future__ import annotations

import json
import logging
import itertools
import queue
import subprocess
import threading
import uuid
from pathlib import Path

from .. import media
from ..sources import media_key
from . import subtitles, transcribe
from .walk import walk
from .matcher import Word, WordList, build_ranges, carry_over

log = logging.getLogger("hush.analysis")


class Analyzer:
    def __init__(self, cfg, db, registry):
        self.cfg = cfg
        self.acfg = cfg.analysis
        self.db = db
        self.registry = registry
        self.wordlist = WordList(self.acfg.wordlist)
        # (priority, order, job id): scans you ask for go ahead of bulk scans
        self.q: queue.PriorityQueue[tuple[int, int, str]] = queue.PriorityQueue()
        self._seq = itertools.count()
        self.on_event = lambda kind, title, message: None   # set by the app to send notifications
        self._batch = {"done": 0, "error": 0}
        self._cancel: set[str] = set()
        self.models_dir = cfg.data_dir / "models"
        self.models_dir.mkdir(exist_ok=True)
        # Scans cut short by a restart pick up again from the start of their title.
        self._resume = db.resume_interrupted_jobs()
        self._go = threading.Event()
        if not db.get_setting("scans_paused", False):
            self._go.set()

    def start(self) -> None:
        for jid in self._resume:
            self.q.put((1, next(self._seq), jid))
        for i in range(max(1, self.acfg.workers)):
            threading.Thread(target=self._worker, name=f"analyzer-{i}", daemon=True).start()

    def engines(self) -> dict:
        return {"whisper": transcribe.available(), "subtitles": True, "default": self.acfg.engine,
                "model": self.acfg.whisper_model}

    # ---- public API -----------------------------------------------------
    def submit(self, source_id: str, item_id: str, title: str = "", engine: str | None = None,
               priority: int = 0) -> dict:
        key = media_key(source_id, item_id)
        active = self.db.active_job_for(key)
        if active:
            return active
        job = {"id": uuid.uuid4().hex[:12], "media_key": key, "source_id": source_id,
               "item_id": item_id, "title": title}
        self.db.create_job(job)
        if engine:
            self.db.update_job(job["id"], stage=f"queued:{engine}")
        self.q.put((priority, next(self._seq), job["id"]))
        return self.db.get_job(job["id"])

    def queue_unscanned(self, source_id: str, entries, retry_failed: bool = False) -> dict:
        """Queue a scan for each entry that has no filter, no active scan and no earlier failure."""
        entries = list(entries)
        keys = {e.id: media_key(e.source or source_id, e.id) for e in entries}
        done = self.db.filtered_keys(list(keys.values()))
        queued = skipped = 0
        for e in entries:
            k = keys[e.id]
            if (k in done or self.db.active_job_for(k)
                    or (not retry_failed and self.db.last_job_blocked(k))):
                skipped += 1
                continue
            self.submit(e.source or source_id, e.id, e.name, priority=1)   # bulk scans wait behind manual ones
            queued += 1
        return {"queued": queued, "skipped": skipped}

    def scan_tree(self, source_id: str, dir_id: str = "", retry_failed: bool = False) -> dict:
        """Queue a scan for every title under a folder that has no filter yet."""
        return self.queue_unscanned(source_id, walk(self.registry.get(source_id), dir_id=dir_id),
                                    retry_failed)

    # ---- queue control ----------------------------------------------------
    @property
    def paused(self) -> bool:
        return not self._go.is_set()

    def pause(self) -> None:
        """Stop starting new scans. A scan already running finishes."""
        self._go.clear()
        self.db.set_setting("scans_paused", True)

    def resume(self) -> None:
        self._go.set()
        self.db.set_setting("scans_paused", False)

    def scan_next(self, job_id: str) -> dict | None:
        """Move a waiting scan to the front of the queue."""
        job = self.db.get_job(job_id)
        if not job or job["status"] != "queued":
            return job
        self.q.put((-1, next(self._seq), job_id))   # the older entry is skipped once this one has run
        return job

    def stop_all(self) -> int:
        """Cancel the running scan and everything waiting."""
        jobs = self.db.active_jobs()
        for j in jobs:
            self.cancel(j["id"])
        return len(jobs)

    def restart(self, job_id: str) -> dict | None:
        """Scan this title again from the start, replacing any scan still active."""
        job = self.db.get_job(job_id)
        if not job:
            return None
        for active in [self.db.active_job_for(job["media_key"])]:
            if active:
                self.cancel(active["id"])
                self.db.update_job(active["id"], status="cancelled", stage="cancelled")
        return self.submit(job["source_id"], job["item_id"], job.get("title") or "")

    def retry_failed(self) -> int:
        n = 0
        for j in self.db.blocked_titles():
            self.submit(j["source_id"], j["item_id"], j.get("title") or "")
            n += 1
        return n

    def cancel(self, job_id: str) -> None:
        self._cancel.add(job_id)
        job = self.db.get_job(job_id)
        if job and job["status"] == "queued":
            self.db.update_job(job_id, status="cancelled", stage="cancelled")

    def rematch(self, key: str) -> dict | None:
        """Re-apply the word list to a cached transcript (no re-transcription)."""
        existing = self.db.get_filter(key)
        words_file = self.cfg.cache_dir / f"{key}.words.json"
        if not existing or not words_file.exists():
            return None
        cached = json.loads(words_file.read_text())
        words = [Word(*w) for w in cached["words"]]
        ranges = self._ranges(words, cached["engine"], existing.get("duration"))
        ranges = carry_over(existing["ranges"], ranges)
        self.db.save_filter(key, existing["source_id"], existing["item_id"], existing["title"],
                            existing["duration"], cached["engine"], ranges)
        return self.db.get_filter(key)

    def reload_wordlist(self) -> None:
        self.wordlist = WordList(self.acfg.wordlist)

    # ---- worker ---------------------------------------------------------
    def _worker(self) -> None:
        while True:
            self._go.wait()
            _, _, job_id = self.q.get()
            self._go.wait()   # paused while this was waiting for a title: hold it
            job = self.db.get_job(job_id)
            if (not job or job["status"] != "queued" or job_id in self._cancel):
                continue          # cancelled, already run, or a duplicate entry from Scan next
            try:
                self._run(job)
            except InterruptedError:
                self.db.update_job(job_id, status="cancelled", stage="cancelled")
            except Exception as exc:  # noqa: BLE001
                log.exception("analysis failed for %s", job.get("title"))
                self.db.update_job(job_id, status="error", stage="error", error=str(exc)[:500])
            finally:
                self._cancel.discard(job_id)
                for f in self.cfg.cache_dir.glob(f"{job_id}.*"):
                    f.unlink(missing_ok=True)
            self._after_job(job_id)

    def _after_job(self, job_id: str) -> None:
        """Count finished scans; when the queue runs dry, report the batch once."""
        status = (self.db.get_job(job_id) or {}).get("status")
        if status in ("done", "error"):
            self._batch["done" if status == "done" else "error"] += 1
        if self.db.active_jobs() or not (self._batch["done"] or self._batch["error"]):
            return
        d, e = self._batch["done"], self._batch["error"]
        self._batch = {"done": 0, "error": 0}
        msg = f"{d} scanned" + (f", {e} failed" if e else "")
        self.on_event("scans_done", "Hush: scans finished", msg)

    def _run(self, job: dict) -> None:
        jid = job["id"]
        requested = (job.get("stage") or "").partition(":")[2] or self.acfg.engine
        self.db.update_job(jid, status="running", stage="probing", progress=0.01)
        src = self.registry.get(job["source_id"])
        ref = src.resolve(job["item_id"])
        info = media.probe(self.cfg.ffprobe, ref, job["source_id"], job["item_id"])
        title = job.get("title") or ref.title
        if not info.audio:
            raise RuntimeError("This file has no audio track")

        engine = requested
        if engine == "auto":
            engine = "whisper" if transcribe.available() else "subtitles"
        if engine == "whisper" and not transcribe.available():
            raise RuntimeError("Whisper engine requested but faster-whisper is not installed")

        if engine == "whisper":
            try:
                words = self._whisper(jid, ref, job, info)
            except InterruptedError:
                raise
            except Exception as exc:  # noqa: BLE001
                if requested != "auto":
                    raise
                # e.g. the model couldn't be downloaded: subtitles are better than nothing
                log.warning("Whisper failed (%s); trying subtitles instead", exc)
                engine = "subtitles"
                try:
                    words = self._subtitles(jid, ref, job, info)
                except RuntimeError:
                    raise RuntimeError(f"Audio scan failed ({exc}) and there are no subtitles to fall back on")
        else:
            words = self._subtitles(jid, ref, job, info)

        self.db.update_job(jid, stage="matching", progress=0.99)
        (self.cfg.cache_dir / f"{job['media_key']}.words.json").write_text(json.dumps(
            {"engine": engine, "words": [[w.text, round(w.start, 3), round(w.end, 3)] for w in words]}))
        ranges = self._ranges(words, engine, info.duration)
        old = self.db.get_filter(job["media_key"])
        if old:
            ranges = carry_over(old["ranges"], ranges)
        self.db.save_filter(job["media_key"], job["source_id"], job["item_id"], title,
                            info.duration, engine, ranges)
        auto = sum(1 for r in ranges if r["source"] == "auto")
        self.db.update_job(jid, status="done", stage=f"{auto} found", progress=1.0)
        log.info("analyzed %s with %s: %d ranges", title, engine, auto)

    def _ranges(self, words: list[Word], engine: str, duration: float | None) -> list[dict]:
        det = self.wordlist.find(words)
        if engine == "subtitles":  # cue-estimated timing: be more generous
            return build_ranges(det, max(0.35, self.acfg.pad_before), max(0.45, self.acfg.pad_after),
                                self.acfg.merge_gap, duration)
        return build_ranges(det, self.acfg.pad_before, self.acfg.pad_after, self.acfg.merge_gap, duration)

    def _check(self, jid: str) -> None:
        if jid in self._cancel:
            raise InterruptedError("cancelled")

    # ---- whisper path ---------------------------------------------------
    def _pick_audio(self, info) -> int:
        lang = (self.acfg.language or "").lower()
        aliases = {"en": {"en", "eng"}, "es": {"es", "spa"}, "fr": {"fr", "fre", "fra"}}
        want = aliases.get(lang, {lang})
        for s in info.audio:
            if s.language.lower() in want:
                return s.index
        default = next((s for s in info.audio if s.default), info.audio[0])
        return default.index

    def _whisper(self, jid: str, ref, job: dict, info) -> list[Word]:
        wav = self.cfg.cache_dir / f"{jid}.wav"
        self.db.update_job(jid, stage="extracting audio", progress=0.02)
        cmd = [self.cfg.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
               *media.ffmpeg_input(ref, job["source_id"], job["item_id"]),
               "-map", f"0:{self._pick_audio(info)}", "-vn", "-sn",
               # Light dialogue emphasis: speech band + loudness normalisation
               "-af", "highpass=f=80,lowpass=f=8000,dynaudnorm",
               "-ac", "1", "-ar", "16000", "-f", "wav", "-progress", "pipe:1", str(wav)]
        self._run_ffmpeg(jid, cmd, info.duration, 0.02, 0.12)
        self.db.update_job(jid, stage=f"transcribing ({self.acfg.whisper_model})", progress=0.12)
        return transcribe.transcribe(
            wav, self.acfg, self.models_dir, info.duration,
            progress=lambda p: self.db.update_job(jid, progress=0.12 + 0.86 * p),
            cancelled=lambda: jid in self._cancel)

    def _run_ffmpeg(self, jid: str, cmd: list[str], duration: float | None, p0: float, p1: float) -> None:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        last = 0.0
        for line in proc.stdout:
            if jid in self._cancel:
                proc.kill()
                proc.wait()
                raise InterruptedError("cancelled")
            if line.startswith("out_time_us=") and duration:
                try:
                    t = int(line.split("=")[1]) / 1e6
                except ValueError:
                    continue
                if t - last > 5:
                    last = t
                    self.db.update_job(jid, progress=p0 + (p1 - p0) * min(1.0, t / duration))
        rc = proc.wait()
        if rc != 0:
            raise RuntimeError(f"ffmpeg failed: {proc.stderr.read()[-400:]}")

    # ---- subtitle path --------------------------------------------------
    def _subtitles(self, jid: str, ref, job: dict, info) -> list[Word]:
        self.db.update_job(jid, stage="reading subtitles", progress=0.05)
        candidates: list[tuple[str, list[dict]]] = []

        for p in ref.subtitle_paths:
            try:
                candidates.append((Path(p).name, subtitles.parse(Path(p).read_text(errors="ignore"))))
            except OSError:
                pass
        for opener in ref.subtitle_openers:
            try:
                with opener() as fh:
                    candidates.append(("sidecar", subtitles.parse(fh.read().decode("utf-8", "ignore"))))
            except Exception:  # noqa: BLE001
                pass

        lang = (self.acfg.language or "en").lower()
        embedded = [s for s in info.subtitles
                    if not s.language or s.language.lower().startswith(lang[:2])
                    or (lang == "en" and s.language.lower() == "eng")]
        for n, s in enumerate(embedded):
            self._check(jid)
            self.db.update_job(jid, stage=f"extracting subtitle track {n + 1}/{len(embedded)}",
                               progress=0.1 + 0.8 * n / max(1, len(embedded)))
            cmd = [self.cfg.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
                   *media.ffmpeg_input(ref, job["source_id"], job["item_id"]),
                   "-map", f"0:{s.index}", "-f", "srt", "pipe:1"]
            try:
                out = subprocess.run(cmd, capture_output=True, timeout=1800, check=True).stdout
                candidates.append((s.label(), subtitles.parse(out.decode("utf-8", "ignore"))))
            except subprocess.SubprocessError as exc:
                log.warning("subtitle track %s failed: %s", s.index, exc)

        candidates = [c for c in candidates if c[1]]
        if not candidates:
            raise RuntimeError("No text subtitles found (embedded or sidecar .srt). "
                               "Install faster-whisper to analyze the audio instead.")
        # "Forced" tracks only cover foreign-language lines: take the fullest track.
        name, cues = max(candidates, key=lambda c: len(c[1]))
        log.info("using subtitles %s (%d cues)", name, len(cues))
        return subtitles.cues_to_words(cues)
