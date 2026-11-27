"""Daily limit, bedtime, now playing and commands to a screen."""
import time

from hush import profiles, watch
from hush.db import DB


def at(hh, mm):
    return time.mktime((2026, 3, 4, hh, mm, 0, 0, 0, -1))


def test_bedtime_across_midnight_and_daily_limit():
    cfg = {"bed_from": "20:30", "bed_to": "07:00", "daily_minutes": 60}
    assert watch.blocked(cfg, 0, at(21, 0)) and watch.blocked(cfg, 0, at(6, 59))
    assert watch.blocked(cfg, 0, at(7, 0)) is None and watch.blocked(cfg, 3599, at(12, 0)) is None
    assert "60 minutes" in watch.blocked(cfg, 3600, at(12, 0))
    assert watch.blocked({}, 10 ** 6) is None
    assert profiles.clean_settings({"daily_minutes": 99999, "bed_from": "25:00", "bed_to": "07:15"}) == {"daily_minutes": 1440, "bed_from": "", "bed_to": "07:15"}


def test_time_counts_only_while_playing_and_commands_reach_the_screen(tmp_path):
    db = DB(tmp_path / "h.db"); w = watch.Watching(db); p = {"id": "k", "name": "Kid"}; t = at(12, 0)
    w.beat("a", p, {"title": "X"}, t)
    w.beat("a", p, {"title": "X"}, t + 10)
    w.beat("a", p, {"title": "X", "paused": True}, t + 20)
    w.beat("a", p, {"title": "X", "paused": True}, t + 30)
    assert db.watch_seconds("k", watch.today(t)) == 20.0
    assert w.command("a", "pause") and not w.command("a", "explode") and not w.command("zz", "stop")
    assert w.beat("a", p, {"title": "X"}, t + 40)["command"] == "pause"
    assert w.beat("a", p, {"title": "X"}, t + 50)["command"] is None
    assert [s["title"] for s in w.active(t + 55)] == ["X"] and w.active(t + 200) == []
