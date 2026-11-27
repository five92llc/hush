"""What is being watched right now, and how long each profile has watched today (for the daily limit and bedtime of kids profiles)."""
from __future__ import annotations

import threading
import time

BEAT = 10           # seconds between a player's reports
GONE = 35           # a screen that has not reported for this long has stopped
COMMANDS = ("pause", "play", "stop")


def today(now: float | None = None) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(now))


def blocked(cfg: dict, used_seconds: float, now: float | None = None) -> str | None:
    """Why this kids profile may not watch right now, or None. ``cfg``: daily_minutes (0 = no limit), bed_from and bed_to as "HH:MM"."""
    a, b = cfg.get("bed_from") or "", cfg.get("bed_to") or ""
    if a and b and a != b:
        clock = time.strftime("%H:%M", time.localtime(now))
        asleep = a <= clock < b if a < b else (clock >= a or clock < b)          # a bedtime usually runs past midnight
        if asleep:
            return f"It is bedtime. Watching starts again at {b}."
    limit = int(cfg.get("daily_minutes") or 0)
    if limit and used_seconds >= limit * 60:
        return f"That is all the watching for today ({limit} minutes)."
    return None


class Watching:
    def __init__(self, db):
        self.db = db
        self.screens: dict[str, dict] = {}
        self._lock = threading.Lock()

    def beat(self, tab: str, profile: dict, info: dict, now: float | None = None) -> dict:
        """A player reports in. Counts the time actually played and hands back any command waiting for that screen."""
        now = now or time.time()
        with self._lock:
            prev = self.screens.get(tab)
            if info.get("closed"):
                self.screens.pop(tab, None)
                return {"command": None}
            if prev and not prev.get("paused") and 0 < now - prev["at"] <= GONE:              # it was playing since the last report
                self.db.add_watch_time(profile["id"], today(now), min(now - prev["at"], BEAT * 2))
            command = (prev or {}).get("command")
            self.screens[tab] = {"tab": tab, "profile_id": profile["id"], "profile": profile["name"], "title": str(info.get("title", ""))[:200],
                                 "position": float(info.get("position") or 0), "duration": float(info.get("duration") or 0),
                                 "paused": bool(info.get("paused")), "live": bool(info.get("live")), "screen": str(info.get("screen", ""))[:60], "at": now, "command": None}
        return {"command": command}

    def active(self, now: float | None = None) -> list[dict]:
        now = now or time.time()
        with self._lock:
            for k in [k for k, v in self.screens.items() if now - v["at"] > GONE]:
                del self.screens[k]
            return [{k: v for k, v in s.items() if k != "command"} for s in sorted(self.screens.values(), key=lambda s: s["profile"])]

    def command(self, tab: str, cmd: str) -> bool:
        with self._lock:
            if tab not in self.screens or cmd not in COMMANDS:
                return False
            self.screens[tab]["command"] = cmd
            return True
