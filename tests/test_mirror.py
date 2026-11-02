"""Screen mirroring: a sender's H.264 becomes a live HLS feed, tokens guard the sender, kids never see the raw feed."""
import subprocess
import time

from fastapi.testclient import TestClient

from hush.app import create_app
from hush.config import Config
from hush.db import DB
from hush.mirror import MirrorHub


def h264(seconds=7) -> bytes:
    return subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30", "-t", str(seconds), "-c:v", "libx264",
                           "-g", "30", "-pix_fmt", "yuv420p", "-bsf:v", "h264_mp4toannexb", "-f", "h264", "-"], capture_output=True, check=True).stdout


def test_a_sent_screen_becomes_a_live_feed(tmp_path):
    cfg = Config(data_dir=tmp_path / "d"); cfg.data_dir.mkdir()
    hub = MirrorHub(cfg, DB(cfg.db_path))
    try:
        assert hub.state()["active"] is False
        s = hub.start_ingest("Test phone")
        data = h264()
        chunks = [data[i:i + 4096] for i in range(0, len(data), 4096)]
        for c in chunks:                                                     # a phone sends in real time
            s.proc.stdin.write(c); s.proc.stdin.flush()
            time.sleep(7.0 / len(chunks))
        end = time.time() + 15
        while time.time() < end and not s.ready:
            time.sleep(0.3)
        st = hub.state()
        assert st["active"] and st["ready"] and st["source"] == "android" and st["name"] == "Test phone", st
        assert hub.file("index.m3u8") and hub.file("../index.m3u8") is None
        hub.stop_session()
        assert hub.state()["active"] is False
    finally:
        hub.shutdown()


def test_settings_are_cleaned_and_the_sender_needs_a_token(tmp_path):
    cfg = Config(password="pw", secret_key="k" * 32, data_dir=tmp_path / "d"); cfg.data_dir.mkdir(); cfg.cache_dir.mkdir()
    c = TestClient(create_app(cfg))
    assert c.put("/api/mirror/settings", json={}).status_code == 401
    c.post("/api/login", json={"password": "pw"})
    st = c.put("/api/mirror/settings", json={"name": "Living<room>!!", "airplay": True}).json()
    assert st["airplay"]["name"] == "Livingroom" and st["airplay"]["enabled"] is True
    tok = c.post("/api/mirror/token").json()
    assert tok["url"].endswith("/api/mirror/ingest") and "." in tok["token"]
    anon = TestClient(create_app(cfg))
    assert anon.post("/api/mirror/ingest", content=b"x").status_code == 401
    assert anon.post("/api/mirror/ingest", content=b"x", headers={"x-hush-token": "9999999999.bad"}).status_code == 401
    assert anon.get("/api/mirror/state").status_code == 401
