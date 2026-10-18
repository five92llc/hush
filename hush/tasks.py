"""Background tasks: a small scheduler for library refresh and clean-up.

Settings and the last result of every task are kept in the database, so they
survive restarts and are edited from the Tasks page.
"""
from __future__ import annotations

import logging
import threading
import time

from .analysis.walk import walk
from .sources import media_key

log = logging.getLogger("hush.tasks")

CATALOG = {
    "refresh": {
        "name": "Library refresh",
        "description": "Looks through your sources for new and removed titles, and can queue scans "
                       "for the new ones.",
    },
    "metadata": {
        "name": "Titles and artwork",
        "description": "Works out each title's name and year, then adds the summary, genres and poster "
                       "(or a thumbnail from the video). Finds new titles first.",
    },
    "cleanup": {
        "name": "Clean up",
        "description": "Removes leftover scan files and scan records older than 30 days.",
    },
}
MIN_HOURS, MAX_HOURS = 0.25, 24 * 30
SOURCE_TIMEOUT = 120      # seconds a source gets to list its titles before it is skipped
STARTUP_DELAY = 30


class TaskManager:
    def __init__(self, cfg, db, registry, analyzer, library=None):
        self.cfg, self.db, self.registry, self.analyzer = cfg, db, registry, analyzer
        self.library = library
        self._running: set[str] = set()
        self._lock = threading.Lock()
        self._started = time.time()

    # ---- settings ----------------------------------------------------------
    def _defaults(self, tid: str) -> dict:
        if tid == "refresh":
            seeded = list(self.cfg.analysis.auto_scan)     # config.yaml's auto_scan turns it on
            return {"enabled": bool(seeded), "interval_hours": self.cfg.analysis.auto_scan_hours,
                    "sources": seeded, "scan_new": True}
        return {"enabled": True, "interval_hours": 24}

    def _state(self) -> dict:
        saved = self.db.get_setting("tasks", {})
        return {tid: {**self._defaults(tid), "last_run": None, "last_status": None,
                      "last_result": "", "last_duration": None, **saved.get(tid, {})}
                for tid in CATALOG}

    def _save(self, tid: str, **fields) -> None:
        saved = self.db.get_setting("tasks", {})
        saved[tid] = {**saved.get(tid, {}), **fields}
        self.db.set_setting("tasks", saved)

    # ---- public API ----------------------------------------------------------
    def list(self) -> dict:
        now = time.time()
        out = []
        for tid, st in self._state().items():
            base = st["last_run"] or self._started + STARTUP_DELAY - st["interval_hours"] * 3600
            out.append({"id": tid, **CATALOG[tid], **st,
                        "running": tid in self._running,
                        "next_run": base + st["interval_hours"] * 3600 if st["enabled"] else None})
        return {"tasks": out, "library": self.db.library_stats(), "now": now,
                "sources": [{"id": s["id"], "name": s["name"], "type": s["type"]} for s in self.registry.list() if "error" not in s]}

    def update(self, tid: str, patch: dict) -> None:
        if tid not in CATALOG:
            raise KeyError(tid)
        clean: dict = {}
        if "enabled" in patch:
            clean["enabled"] = bool(patch["enabled"])
        if "interval_hours" in patch:
            hours = float(patch["interval_hours"])
            if not MIN_HOURS <= hours <= MAX_HOURS:
                raise ValueError("The interval must be between 15 minutes and 30 days")
            clean["interval_hours"] = hours
        if tid == "refresh":
            if "scan_new" in patch:
                clean["scan_new"] = bool(patch["scan_new"])
            if "sources" in patch:
                known = {s["id"] for s in self.registry.list() if "error" not in s}
                clean["sources"] = [s for s in patch["sources"] if s in known]
        self._save(tid, **clean)

    def run(self, tid: str) -> bool:
        """Start a task in the background. False if it is already running."""
        if tid not in CATALOG:
            raise KeyError(tid)
        with self._lock:
            if tid in self._running:
                return False
            self._running.add(tid)
        threading.Thread(target=self._execute, args=(tid,), name=f"task-{tid}", daemon=True).start()
        return True

    # ---- scheduler ---------------------------------------------------------------
    def start(self) -> None:
        threading.Thread(target=self._loop, name="tasks", daemon=True).start()

    def _loop(self) -> None:
        time.sleep(STARTUP_DELAY)
        while True:
            now = time.time()
            for t in self.list()["tasks"]:
                if t["enabled"] and not t["running"] and t["next_run"] and now >= t["next_run"]:
                    self.run(t["id"])
            time.sleep(20)

    def _execute(self, tid: str) -> None:
        started = time.time()
        try:
            result = getattr(self, f"_{tid}")(self._state()[tid])
            status = "ok"
        except Exception as exc:  # noqa: BLE001
            log.exception("task %s failed", tid)
            result, status = str(exc)[:300] or "failed", "error"
            self.analyzer.on_event("failure", f"Hush: {CATALOG[tid]['name']} failed", result)
        # Save the result before the task stops counting as running, so nobody reads a stale one.
        self._save(tid, last_run=started, last_status=status, last_result=result,
                   last_duration=round(time.time() - started, 1))
        self._running.discard(tid)

    # ---- the tasks -----------------------------------------------------------------
    def _refresh(self, opts: dict) -> str:
        ids = [s for s in opts["sources"] if s in {x["id"] for x in self.registry.list()}]
        if not ids:
            return "No sources selected"
        summary, new = self._index(ids, bool(opts.get("scan_new")))
        if new and self.library:
            self.run("metadata")           # new titles get their details right away
        return summary

    def _index(self, ids: list[str], scan_new: bool) -> tuple[str, int]:
        opts = {"scan_new": scan_new}
        started = time.time()
        titles = new = removed = queued = 0
        problems: list[str] = []
        for sid in ids:
            errors: list[str] = []
            entries = self._list_source(sid, errors)
            problems += errors
            rows = [(media_key(e.source or sid, e.id), e.source or sid, e.id, e.name) for e in entries]
            new += self.db.record_library(sid, rows, started)
            if not errors:                      # a half-read source must not look like deletions
                removed += self.db.prune_library(sid, started)
            titles += len(rows)
            if opts.get("scan_new"):
                queued += self.analyzer.queue_unscanned(sid, entries)["queued"]
        parts = [f"{titles} titles", f"{new} new", f"{removed} removed"]
        if opts.get("scan_new"):
            parts.append(f"{queued} scans queued")
        if problems:
            parts.append(f"{len(problems)} folders could not be opened")
        return ", ".join(parts), new

    def _list_source(self, sid: str, errors: list[str]) -> list:
        """Every title of a source, or [] if it does not finish in time.
        A source that does not answer (a NAS that is off) must not hold up the others."""
        found: list = []
        done = threading.Event()

        def run() -> None:
            try:
                for e in walk(self.registry.get(sid), errors):
                    found.append(e)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{sid}: {exc}")
            done.set()

        threading.Thread(target=run, name=f"walk-{sid}", daemon=True).start()
        if not done.wait(SOURCE_TIMEOUT):
            errors.append(f"{sid}: did not answer in {SOURCE_TIMEOUT} s")
            return []              # an incomplete list is ignored, so nothing looks deleted
        return found

    def _metadata(self, opts: dict) -> str:
        if not self.library:
            return "Not available"
        self._index([s["id"] for s in self.registry.list() if "error" not in s], False)   # make sure the list is current
        r = self.library.process_library()
        left = len(self.db.library_without_meta())
        return f"{r['processed']} titles filled in" + (f", {r['failed']} failed" if r["failed"] else "") + \
               (f", {left} still waiting" if left else "")

    def _cleanup(self, opts: dict) -> str:
        active = {j["id"] for j in self.db.active_jobs()}
        files = 0
        for f in self.cfg.cache_dir.glob("*"):
            if f.suffix in (".wav", ".tmp") and f.stem not in active and time.time() - f.stat().st_mtime > 3600:
                f.unlink(missing_ok=True)
                files += 1
        jobs = self.db.delete_old_jobs(time.time() - 30 * 86400)
        return f"{files} leftover files and {jobs} old scan records removed"
