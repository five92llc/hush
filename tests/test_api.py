"""End-to-end API tests against real media generated with ffmpeg."""
import re
import subprocess
import time

import pytest
import yaml
from fastapi.testclient import TestClient

from hush.app import create_app
from hush.config import load_config

SRT = """1
00:00:01,000 --> 00:00:02,500
Hello there.

2
00:00:04,000 --> 00:00:05,500
What the hell is that?

3
00:00:07,000 --> 00:00:08,500
Get the fuck out!
"""


def ff(*args):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    d = tmp_path_factory.mktemp("media")
    (d / "subs.srt").write_text(SRT)
    lavfi_v = ["-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24"]
    lavfi_a = ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000"]
    ff(*lavfi_v, *lavfi_a, "-i", str(d / "subs.srt"), "-t", "10", "-map", "0", "-map", "1", "-map", "2",
       "-c:v", "libx264", "-g", "24", "-pix_fmt", "yuv420p", "-c:a", "ac3", "-c:s", "srt",
       "-metadata:s:s:0", "language=eng", str(d / "movie.mkv"))
    ff(*lavfi_v, *lavfi_a, "-t", "4", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(d / "clip.mp4"))
    ff(*lavfi_v, *lavfi_a, "-t", "3", "-c:v", "mpeg4", "-c:a", "libmp3lame", str(d / "old.avi"))
    ff("-f", "lavfi", "-i", "sine=frequency=500", "-t", "3", str(d / "song.mp3"))
    ff("-f", "lavfi", "-i", "sine=frequency=500", "-t", "3", str(d / "tone.wav"))
    (d / "notes.txt").write_text("not media")
    return d


@pytest.fixture(scope="module")
def client(media, tmp_path_factory):
    data = tmp_path_factory.mktemp("data")
    cfg_file = data / "config.yaml"
    cfg_file.write_text(yaml.safe_dump({
        "data_dir": str(data), "password": "secret",
        "sources": [{"id": "lib", "type": "local", "name": "Library", "path": str(media)}]}))
    with TestClient(create_app(load_config(cfg_file))) as c:
        yield c


def login(c):
    assert c.post("/api/login", json={"password": "secret"}).status_code == 200


def entries(c):
    return {e["name"]: e for e in c.get("/api/browse/lib").json()}


def test_requires_login(client):
    client.cookies.clear()
    assert client.get("/api/sources").status_code == 401
    assert client.post("/api/login", json={"password": "nope"}).status_code == 401
    login(client)
    assert client.get("/api/sources").status_code == 200


def test_browse_lists_only_media(client):
    login(client)
    assert set(entries(client)) == {"movie.mkv", "clip.mp4", "old.avi", "song.mp3", "tone.wav"}


def test_path_traversal_blocked(client):
    login(client)
    from hush.sources.base import enc
    r = client.get(f"/api/media/lib/{enc('0:../../etc/passwd')}")
    assert r.status_code == 400


@pytest.mark.parametrize("name,mode", [("clip.mp4", "direct"), ("movie.mkv", "remux"),
                                       ("old.avi", "transcode"), ("song.mp3", "direct"), ("tone.wav", "direct")])
def test_play_modes(client, name, mode):
    login(client)
    e = entries(client)[name]
    assert client.get(f"/api/media/lib/{e['id']}").json()["mode"] == mode


def test_range_requests(client):
    login(client)
    e = entries(client)["clip.mp4"]
    r = client.get(f"/api/raw/lib/{e['id']}", headers={"Range": "bytes=10-19"})
    assert r.status_code == 206 and len(r.content) == 10
    assert r.headers["content-range"].startswith("bytes 10-19/")


def test_live_stream_is_playable_mp4(client, tmp_path):
    login(client)
    e = entries(client)["old.avi"]
    out = tmp_path / "s.mp4"
    out.write_bytes(client.get(f"/api/stream/lib/{e['id']}").content)
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(out)],
                           capture_output=True, text=True).stdout.split()
    assert probe == ["h264", "aac"]


def _scan(client, item_id, engine=None):
    job = client.post("/api/analyze", json={"source_id": "lib", "item_id": item_id, "engine": engine}).json()
    for _ in range(100):
        job = client.get(f"/api/jobs/{job['id']}").json()
        if job["status"] not in ("queued", "running"):
            return job
        time.sleep(0.1)
    raise AssertionError("scan did not finish")


def test_scan_from_subtitles_and_edit(client):
    login(client)
    e = entries(client)["movie.mkv"]
    job = _scan(client, e["id"], "subtitles")
    assert job["status"] == "done", job
    f = client.get(f"/api/filters/{e['media_key']}").json()
    words = [w for r in f["ranges"] for w in r["words"]]
    assert words == ["hell", "fuck"]
    assert all(r["enabled"] for r in f["ranges"])
    assert entries(client)["movie.mkv"]["filtered"]

    # switch one off and add a manual mark; both must survive a rescan
    f["ranges"][0]["enabled"] = False
    f["ranges"].append({"start": 1.0, "end": 1.5, "source": "manual", "category": "manual"})
    r = client.put(f"/api/filters/{e['media_key']}", json={"source_id": "lib", "item_id": e["id"], "ranges": f["ranges"]})
    assert r.status_code == 200
    _scan(client, e["id"], "subtitles")
    f2 = client.get(f"/api/filters/{e['media_key']}").json()
    assert [r["source"] for r in f2["ranges"]] == ["manual", "auto", "auto"]
    assert f2["ranges"][1]["enabled"] is False

    edl = client.get(f"/api/filters/{e['media_key']}/export?format=edl").text.strip().splitlines()
    assert len(edl) == 2 and all(line.endswith("\t1") for line in edl)


def test_filtered_external_stream_is_silent_in_ranges(client, tmp_path):
    login(client)
    e = entries(client)["movie.mkv"]
    url = client.get(f"/api/external/lib/{e['id']}").json()["url"]
    path = url.split("testserver", 1)[1]
    anon = TestClient(client.app)
    assert anon.get(f"/api/filtered/lib/{e['id']}.mkv").status_code == 401   # needs signature
    out = tmp_path / "f.mkv"
    out.write_bytes(anon.get(path).content)
    log = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(out), "-af",
                          "asetnsamples=4800,astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    levels = {round(float(t), 1): v for t, v in re.findall(r"pts_time:([\d.]+)\s*\n.*RMS_level=(\S+)", log)}
    f = client.get(f"/api/filters/{e['media_key']}").json()
    on = [r for r in f["ranges"] if r["enabled"]]
    assert on, "expected at least one enabled range"
    for r in on:
        mid = round((r["start"] + r["end"]) / 2, 1)
        assert levels.get(mid) == "-inf", (mid, levels.get(mid))
    assert levels.get(2.0) != "-inf"   # untouched dialogue still plays


def test_internal_raw_needs_token(client):
    e = entries(client)["clip.mp4"]
    assert client.get(f"/internal/raw/lib/{e['id']}?k=wrong").status_code == 403


def test_whisper_path_with_stub_model(client, monkeypatch):
    """Runs the real audio extraction and pipeline; only the speech model is stubbed."""
    from types import SimpleNamespace as NS
    from hush.analysis import transcribe

    class FakeModel:
        def transcribe(self, path, **kw):
            assert kw["word_timestamps"] is True
            assert open(path, "rb").read(4) == b"RIFF"          # ffmpeg produced a wav
            seg = NS(end=3.0, words=[NS(word=" Well,", start=0.5, end=0.8), NS(word=" damn", start=0.9, end=1.2),
                                     NS(word=" it", start=1.2, end=1.4)])
            return iter([seg]), NS(duration=3.0)

    monkeypatch.setattr(transcribe, "available", lambda: True)
    monkeypatch.setattr(transcribe, "_load", lambda cfg, d: FakeModel())
    login(client)
    e = entries(client)["clip.mp4"]
    job = _scan(client, e["id"])
    assert job["status"] == "done", job
    f = client.get(f"/api/filters/{e['media_key']}").json()
    assert f["engine"] == "whisper"
    (r,) = f["ranges"]
    assert r["words"] == ["damn it"] or r["words"] == ["damn", "it"] or r["words"] == ["damn"]
    assert 0.7 <= r["start"] <= 0.9 and 1.2 <= r["end"] <= 1.7
