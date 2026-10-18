"""HLS output for browsers that cannot play a live fragmented-MP4 stream (Safari, iOS).

Each playback start launches one ffmpeg that writes a playlist and 4 s MPEG-TS segments
into a temporary folder. Idle sessions are stopped and deleted; one browser tab owns at
most one session, so seeking replaces the old one.
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
from typing import Callable

log = logging.getLogger("hush.hls")
IDLE_SECONDS = 120
MAX_SESSIONS = 6
NAME = re.compile(r"^[A-Za-z0-9_.-]+\.(m3u8|ts)$")


class HLSError(Exception):
    pass


class Session:
    def __init__(self, sid: str, owner: str, folder: Path, proc: subprocess.Popen):
        self.sid, self.owner, self.folder, self.proc = sid, owner, folder, proc
        self.last = time.time()


class HLSManager:
    def __init__(self, root: Path):
        self.root = root
        shutil.rmtree(root, ignore_errors=True)          # leftovers from a crash or restart
        root.mkdir(parents=True, exist_ok=True)
        self.sessions: dict[str, Session] = {}
        self._lock = threading.Lock()
        threading.Thread(target=self._reap, name="hls-reaper", daemon=True).start()

    # ---- starting ----------------------------------------------------------
    def create(self, build_cmd: Callable[[Path], list[str]], owner: str, timeout: float = 45.0) -> str:
        sid = uuid.uuid4().hex[:12]
        folder = self.root / sid
        folder.mkdir()
        with self._lock:
            for s in [s for s in self.sessions.values() if owner and s.owner == owner]:
                self._stop(s)                              # this tab is playing something else now
            while len(self.sessions) >= MAX_SESSIONS:
                self._stop(min(self.sessions.values(), key=lambda s: s.last))
            log_file = open(folder / "ffmpeg.log", "wb")
            proc = subprocess.Popen(build_cmd(folder), stdout=subprocess.DEVNULL, stderr=log_file)
            self.sessions[sid] = Session(sid, owner, folder, proc)
        try:
            self._wait_ready(sid, timeout)
        except HLSError:
            with self._lock:
                if sid in self.sessions:
                    self._stop(self.sessions[sid])
            raise
        return sid

    def _wait_ready(self, sid: str, timeout: float) -> None:
        s = self.sessions[sid]
        playlist = s.folder / "index.m3u8"
        end = time.time() + timeout
        while time.time() < end:
            if playlist.exists() and ".ts" in playlist.read_text(errors="ignore"):
                return
            if s.proc.poll() is not None and not (playlist.exists() and ".ts" in playlist.read_text(errors="ignore")):
                tail = (s.folder / "ffmpeg.log").read_text(errors="ignore")[-300:].strip()
                raise HLSError(f"ffmpeg stopped: {tail or 'unknown error'}")
            time.sleep(0.15)
        raise HLSError("The stream did not start in time")

    # ---- serving ---------------------------------------------------------------
    def file(self, sid: str, name: str) -> Path | None:
        if not NAME.match(name):
            return None
        with self._lock:
            s = self.sessions.get(sid)
            if not s:
                return None
            s.last = time.time()
        p = s.folder / name
        return p if p.is_file() else None

    # ---- stopping -------------------------------------------------------------------
    def _stop(self, s: Session) -> None:
        self.sessions.pop(s.sid, None)
        if s.proc.poll() is None:
            s.proc.kill()
        try:
            s.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        shutil.rmtree(s.folder, ignore_errors=True)

    def stop_all(self) -> None:
        with self._lock:
            for s in list(self.sessions.values()):
                self._stop(s)

    def _reap(self) -> None:
        while True:
            time.sleep(10)
            with self._lock:
                for s in [s for s in self.sessions.values() if time.time() - s.last > IDLE_SECONDS]:
                    self._stop(s)
