"""Screen mirroring into Hush: an iPhone, iPad or Mac (AirPlay) or an Android phone or tablet (the Hush app) shows its screen on a Hush screen.

Everything ends up as one live HLS feed in a folder, which the Hush screens play. AirPlay is received by UxPlay running on a hidden display
(Xvfb) with a virtual sound card (PulseAudio); ffmpeg watches both. Android sends its screen as H.264 straight to ``/api/mirror/ingest``.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

log = logging.getLogger("hush.mirror")
NAME = re.compile(r"^[A-Za-z0-9_.-]+\.(m3u8|ts)$")
DISPLAY = ":99"
WIDTH, HEIGHT = 1280, 720
DEFAULTS = {"airplay": False, "name": "Hush", "pin": False, "android": True}
NEEDED = ("uxplay", "Xvfb", "pulseaudio", "xwininfo", "pactl")
HLS_OUT = ["-f", "hls", "-hls_time", "1", "-hls_list_size", "5", "-hls_flags", "delete_segments+independent_segments+omit_endlist", "-hls_segment_filename"]


class Session:
    """One live feed being written to a folder."""
    def __init__(self, source: str, name: str, folder: Path, proc: subprocess.Popen):
        self.sid = folder.name
        self.source, self.name, self.folder, self.proc = source, name, folder, proc
        self.started = time.time()
        self.last = time.time()
        self.bytes = 0

    @property
    def alive(self) -> bool:
        return self.proc.poll() is None

    @property
    def ready(self) -> bool:
        try:
            return ".ts" in (self.folder / "index.m3u8").read_text(errors="ignore")
        except OSError:
            return False


class MirrorHub:
    def __init__(self, cfg, db):
        self.cfg, self.db = cfg, db
        self.root = cfg.data_dir / "mirror"
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)
        self.session: Session | None = None
        self.procs: dict[str, subprocess.Popen] = {}
        self.sig = ""
        self._idle = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.rt = Path("/tmp") / f"hush-rt-{os.getuid()}" if hasattr(os, "getuid") else Path("/tmp/hush-rt")
        threading.Thread(target=self._watch, name="mirror-watch", daemon=True).start()

    # ---- settings -------------------------------------------------------------------------------------
    def config(self) -> dict:
        return {**DEFAULTS, **(self.db.get_setting("mirror", None) or {})}

    def set_config(self, new: dict) -> dict:
        cur = self.config()
        out = {"airplay": bool(new.get("airplay", cur["airplay"])), "android": bool(new.get("android", cur["android"])),
               "pin": bool(new.get("pin", cur["pin"])), "name": (re.sub(r"[^\w .-]", "", str(new.get("name", cur["name"]))).strip()[:30] or "Hush")}
        self.db.set_setting("mirror", out)
        return out

    def missing(self) -> list[str]:
        if not sys.platform.startswith("linux"):
            return ["Linux"]
        return [b for b in NEEDED if not shutil.which(b)]

    # ---- AirPlay: UxPlay on a hidden display ------------------------------------------------------------
    def _env(self) -> dict:
        return {**os.environ, "DISPLAY": DISPLAY, "XDG_RUNTIME_DIR": str(self.rt), "PULSE_SINK": "hushmirror", "PULSE_SERVER": f"unix:{self.rt}/pulse/native"}

    def _spawn(self, key: str, cmd: list[str]) -> None:
        p = self.procs.get(key)
        if p and p.poll() is None:
            return
        log_file = open(self.root / f"{key}.log", "wb")
        self.procs[key] = subprocess.Popen(cmd, env=self._env(), stdout=log_file, stderr=log_file, stdin=subprocess.DEVNULL, start_new_session=True)

    def _ensure_stack(self, c: dict) -> None:
        sig = f"{c['name']}|{c['pin']}"
        if self.sig and sig != self.sig:
            self._kill("uxplay")
        self.sig = sig
        (self.rt / "pulse").mkdir(parents=True, exist_ok=True)
        self.rt.chmod(0o700)
        self._spawn("xvfb", ["Xvfb", DISPLAY, "-screen", "0", f"{WIDTH}x{HEIGHT}x24", "-nolisten", "tcp"])
        if "pulse" not in self.procs or self.procs["pulse"].poll() is not None:
            subprocess.run(["pulseaudio", "-k"], env=self._env(), capture_output=True)
            time.sleep(0.3)
            self._spawn("pulse", ["pulseaudio", "-n", "--exit-idle-time=-1", "--load=module-native-protocol-unix socket=" + f"{self.rt}/pulse/native",
                                  "--load=module-null-sink sink_name=hushmirror", "--log-target=stderr"])
            time.sleep(1.2)
        sink = f"videoscale add-borders=true ! video/x-raw,width={WIDTH},height={HEIGHT} ! ximagesink"
        cmd = ["uxplay", "-n", c["name"], "-nh", "-s", f"{WIDTH}x{HEIGHT}", "-vs", sink, "-as", "pulsesink"]
        if c["pin"]:
            cmd += ["-pin"]
        self._spawn("uxplay", cmd)

    def _kill(self, key: str) -> None:
        p = self.procs.pop(key, None)
        if p and p.poll() is None:
            try:
                os.killpg(p.pid, 15)
            except OSError:
                p.kill()
            try:
                p.wait(timeout=4)
            except subprocess.TimeoutExpired:
                p.kill()

    def _kill_stack(self) -> None:
        for k in ("uxplay", "pulse", "xvfb"):
            self._kill(k)

    def _screen_busy(self) -> bool:
        """True while a sender is mirroring: UxPlay's video window exists only then."""
        try:
            out = subprocess.run(["xwininfo", "-root", "-tree"], env=self._env(), capture_output=True, text=True, timeout=3).stdout
        except (OSError, subprocess.SubprocessError):
            return False
        m = re.search(r"(\d+) child", out)
        return bool(m and int(m.group(1)) > 0)

    def _new_folder(self) -> Path:
        d = self.root / uuid.uuid4().hex[:12]
        d.mkdir()
        return d

    def _start_airplay_capture(self) -> None:
        d = self._new_folder()
        cmd = [self.cfg.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-f", "x11grab", "-framerate", "30", "-video_size", f"{WIDTH}x{HEIGHT}", "-i", DISPLAY,
               "-f", "pulse", "-i", "hushmirror.monitor", "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", "-g", "30", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "128k", *HLS_OUT, str(d / "seg%d.ts"), str(d / "index.m3u8")]
        proc = subprocess.Popen(cmd, env=self._env(), stdout=subprocess.DEVNULL, stderr=open(d / "ffmpeg.log", "wb"), stdin=subprocess.DEVNULL)
        self._set(Session("airplay", "an Apple device", d, proc))

    # ---- Android (and anything else that can send H.264) ----------------------------------------------------
    def start_ingest(self, name: str) -> Session:
        d = self._new_folder()
        cmd = [self.cfg.ffmpeg, "-hide_banner", "-loglevel", "error", "-fflags", "nobuffer", "-probesize", "50000", "-analyzeduration", "300000", "-use_wallclock_as_timestamps", "1", "-f", "h264", "-i", "pipe:0",
               "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "64k",
               *HLS_OUT, str(d / "seg%d.ts"), str(d / "index.m3u8")]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=open(d / "ffmpeg.log", "wb"))
        s = Session("android", name[:40] or "an Android device", d, proc)
        self._set(s)
        return s

    # ---- the one active feed ------------------------------------------------------------------------------------
    def _set(self, s: Session) -> None:
        with self._lock:
            old, self.session = self.session, s
        if old:
            self._end(old)

    def _end(self, s: Session) -> None:
        try:
            if s.proc.stdin:
                s.proc.stdin.close()
        except OSError:
            pass
        if s.proc.poll() is None:
            s.proc.terminate()
            try:
                s.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                s.proc.kill()
        threading.Timer(15, shutil.rmtree, args=(s.folder,), kwargs={"ignore_errors": True}).start()

    def stop_session(self) -> None:
        with self._lock:
            s, self.session = self.session, None
        if s:
            self._end(s)

    def _watch(self) -> None:
        while not self._stop.is_set():
            time.sleep(1)
            try:
                c = self.config()
                if c["airplay"] and not self.missing():
                    self._ensure_stack(c)
                    busy = self._screen_busy()
                    s = self.session
                    if busy and s is None:
                        self._start_airplay_capture()
                    if s and s.source == "airplay":
                        self._idle = 0 if busy else self._idle + 1
                        if self._idle >= 3 or not s.alive:
                            self.stop_session(); self._idle = 0
                elif self.procs:
                    self._kill_stack()
                s = self.session
                if s and s.source == "android" and not s.alive:
                    self.stop_session()
            except Exception:                       # the watcher must never die
                log.exception("mirror watcher")

    def shutdown(self) -> None:
        self._stop.set()
        self.stop_session()
        self._kill_stack()

    # ---- what the screens see --------------------------------------------------------------------------------------
    def state(self) -> dict:
        c, s = self.config(), self.session
        return {"active": bool(s and s.alive), "ready": bool(s and s.alive and s.ready), "source": s.source if s else "", "name": s.name if s else "", "since": s.started if s else 0,
                "sid": s.sid if s else "", "airplay": {"enabled": c["airplay"], "name": c["name"], "pin": c["pin"], "running": bool(self.procs.get("uxplay") and self.procs["uxplay"].poll() is None),
                                                      "missing": self.missing()}, "android": c["android"]}

    def file(self, name: str) -> Path | None:
        s = self.session
        if not s or not NAME.match(name):
            return None
        s.last = time.time()
        p = s.folder / name
        return p if p.is_file() else None
