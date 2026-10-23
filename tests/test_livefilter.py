"""Live TV caption filter: windows, playlist, and a real run against a looping test feed."""
import re
import subprocess
import time

import pytest

from hush import livefilter
from hush.analysis.matcher import WordList
from hush.config import Config


def test_mute_expression_and_playlist_parsing():
    assert livefilter.mute_expression([(1.0, 2.5), (4.0, 4.5)]) == "volume=enable='between(t,1.000,2.500)+between(t,4.000,4.500)':volume=0"
    text = "#EXTM3U\n#EXT-X-VERSION:3\n#EXTINF:2.000,\ns000000.ts\n#EXTINF:3.400,\ns000001.ts\n"
    assert livefilter.parse_playlist(text) == [("s000000.ts", 2.0), ("s000001.ts", 3.4)]


def test_captions_become_mute_windows_per_segment(tmp_path):
    live = livefilter.LiveFilter(Config(data_dir=tmp_path), WordList(), tmp_path / "lf")
    s = livefilter.Session(live, "k", tmp_path / "lf" / "abc", [], None, False)
    s.add_cues([{"start": 10.0, "end": 12.0, "text": "well that is some shit"}, {"start": 20.0, "end": 22.0, "text": "a lovely day"}])
    assert s.cues_seen and len(s.ranges) == 1
    r = s.ranges[0]
    assert r["start"] < 12.0 and r["end"] > 11.0                  # around the flagged word, padded
    seg_in = {"t0": 9.0, "dur": 4.0}
    seg_out = {"t0": 20.0, "dur": 2.0}
    (a, b), = s.windows_for(seg_in)
    assert 0 <= a < b <= 4.0
    assert s.windows_for(seg_out) == []
    s.add_cues([{"start": 10.0, "end": 12.0, "text": "well that is some shit"}])   # the same cue again changes nothing
    assert len(s.cues) == 2
    live.stop_all()


def test_a_category_choice_limits_what_is_muted(tmp_path):
    live = livefilter.LiveFilter(Config(data_dir=tmp_path), WordList(), tmp_path / "lf")
    s = livefilter.Session(live, "k", tmp_path / "lf" / "abc", [], {"slurs"}, False)
    s.add_cues([{"start": 1.0, "end": 3.0, "text": "what the shit"}])
    assert s.ranges == []
    live.stop_all()


def volume_of(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"mean_volume: (-?[\d.]+|-inf) dB", r.stderr)
    return float("-inf") if not m or m.group(1) == "-inf" else float(m.group(1))


def test_live_run_delays_mutes_and_keeps_the_rest(tmp_path, monkeypatch):
    monkeypatch.setattr(livefilter, "DELAY", 2.0)
    feed = tmp_path / "feed.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=15",
                    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100", "-t", "24", "-c:v", "libx264", "-g", "30", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(feed)], check=True)
    cfg = Config(data_dir=tmp_path)
    live = livefilter.LiveFilter(cfg, WordList(), tmp_path / "lf", realtime_inputs=True)
    owner = "tab1"
    sess = None
    try:
        # captions arrive with the segments in real life; here they are given up front for 7-9 s
        key_args = ["-i", str(feed)]
        sess = livefilter.Session(live, "k|*|0", tmp_path / "lf" / "manual", key_args, None, False)
        live.sessions["k|*|0"] = sess
        sess.start()
        sess.add_cues([{"start": 7.0, "end": 9.0, "text": "oh shit"}])
        end = time.time() + 40
        while time.time() < end and len(sess.published) < 7:
            time.sleep(0.5)
        assert len(sess.published) >= 7, sess.status()
        assert sess.muted >= 1
        pl = (sess.out / "index.m3u8").read_text()
        assert pl.startswith("#EXTM3U") and ".ts" in pl
        volumes = []
        for p in sess.published:
            seg = next(s for s in sess.segments if s["name"] == p["name"])
            volumes.append((seg["t0"], seg["t0"] + seg["dur"], volume_of(sess.out / p["name"])))
        assert max(v for _, _, v in volumes) > -30                                   # untouched segments still carry the tone
        # "shit" is estimated at about 7.9 s; the window runs from about 6.3 s to 9.9 s, so the segments from 6 to 10 s are mostly silent
        muted = [v for a, b, v in volumes if a >= 6.0 and b <= 10.0]
        clear = [v for a, b, v in volumes if b <= 6.0 or a >= 11.0]
        assert muted and clear and max(muted) < min(clear) - 6, volumes             # at least 6 dB quieter than the untouched ones
    finally:
        live.stop_all()


def test_a_backlog_at_the_start_does_not_make_the_viewer_watch_old_content(tmp_path, monkeypatch):
    monkeypatch.setattr(livefilter, "DELAY", 0.5)
    live = livefilter.LiveFilter(Config(data_dir=tmp_path), WordList(), tmp_path / "lf")
    s = livefilter.Session(live, "k", tmp_path / "lf" / "abc", [], None, False)
    s.mode = "captions"
    published = []
    s._publish = lambda seg: published.append(seg["seq"]) or s.published.append({"name": seg["name"], "dur": seg["dur"], "seq": seg["seq"]})
    now = time.time()
    for i in range(30):                                       # 30 segments arrive at once
        s.segments.append({"seq": i, "name": f"s{i:06d}.ts", "dur": 2.0, "t0": i * 2.0, "ready": now - 5, "extracted": True})
    threading = __import__("threading")
    threading.Thread(target=s._publish_loop, daemon=True).start()
    time.sleep(1.2)
    s.stop_event.set()
    assert published and published[0] >= 26                  # starts near the newest, not at segment 0
    live.stop_all()


class FakeASR:
    """Stands in for Whisper: every 8 s window "hears" the same two words at the same places inside it."""
    def __init__(self):
        self.active, self.calls = 0, 0

    def available(self):
        return True

    def claim(self):
        self.active += 1
        return True

    def release(self):
        self.active -= 1

    def words(self, wav):
        from hush.analysis.matcher import Word
        self.calls += 1
        return [Word("well", 1.0, 1.3), Word("shit", 3.0, 3.4), Word("okay", 5.0, 5.3)]


def test_a_channel_without_captions_is_filtered_by_speech_recognition(tmp_path, monkeypatch):
    monkeypatch.setattr(livefilter, "DELAY", 2.0)
    monkeypatch.setattr(livefilter, "CC_PROBE_SECONDS", 1.0)
    feed = tmp_path / "feed.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=15",
                    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100", "-t", "26", "-c:v", "libx264", "-g", "30", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(feed)], check=True)
    asr = FakeASR()
    live = livefilter.LiveFilter(Config(data_dir=tmp_path), WordList(), tmp_path / "lf", realtime_inputs=True, asr=asr)
    try:
        sess = livefilter.Session(live, "k|*|0", tmp_path / "lf" / "manual", ["-i", str(feed)], None, False)
        live.sessions["k|*|0"] = sess
        sess.start()
        end = time.time() + 40
        while time.time() < end and len(sess.published) < 7:
            time.sleep(0.5)
        st = sess.status()
        assert st["mode"] == "asr" and st["words"] > 0 and not st["behind"], st
        assert sess.muted >= 1 and asr.calls >= 2, (st, asr.calls)
        assert asr.active == 1
        assert sess.covered_until >= sess.segments[sess.published[-1]["seq"]]["t0"], "published audio that was never checked"
    finally:
        live.stop_all()
    assert asr.active == 0                                   # the recognition slot is given back


def test_a_kids_session_is_refused_when_nothing_can_check_the_audio(tmp_path, monkeypatch):
    monkeypatch.setattr(livefilter, "DELAY", 0.3)
    monkeypatch.setattr(livefilter, "CC_PROBE_SECONDS", 0.5)
    monkeypatch.setattr(livefilter, "STRICT_GIVE_UP", 3.0)

    class NoASR(FakeASR):
        def available(self):
            return False
    live = livefilter.LiveFilter(Config(data_dir=tmp_path), WordList(), tmp_path / "lf", asr=NoASR())
    s = livefilter.Session(live, "k", tmp_path / "lf" / "abc", [], None, True)
    s.segments.append({"seq": 0, "name": "s000000.ts", "dur": 2.0, "t0": 0.0, "ready": time.time() - 5, "extracted": True})
    import threading
    threading.Thread(target=s._publish_loop, daemon=True).start()
    s.started = time.time() - 4                              # nothing has been decided for longer than a kids session will wait
    s._decide_mode()
    time.sleep(1.0)
    assert s.stop_event.is_set() and s.state == "nocaptions" and s.published == []
    live.stop_all()


def test_captions_feed_drops_rolled_up_repeats_and_chunks_long_lines(tmp_path):
    live = livefilter.LiveFilter(Config(data_dir=tmp_path), WordList(), tmp_path / "lf", realtime_inputs=True)
    sess = livefilter.Session(live, "k|*|0", tmp_path / "lf" / "m", ["-i", "x"], None, False)
    sess._caption(0, 2, "good evening and welcome")
    sess._caption(2, 4, "and welcome to the news tonight")        # roll-up: "and welcome" was already shown
    out = sess.captions_after(0)
    assert [c["text"] for c in out["cues"]] == ["good evening and welcome", "to the news tonight"]
    assert out["next"] == 2 and sess.captions_after(out["next"])["cues"] == []
    sess._caption(4, 8, " ".join(f"w{i}" for i in range(20)))
    assert max(len(c["text"].split()) for c in sess.captions_after(2)["cues"]) <= livefilter.CAPTION_WORDS
