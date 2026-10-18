"""Link handling: smb/ftp/sftp URLs, live streams and scheme validation."""
import pytest

from hush.sources.base import SourceError, dec, enc
from hush.sources.links import LinkSource, clean, scheme


@pytest.fixture()
def links():
    return LinkSource({"id": "url", "type": "link"})


def test_clean_strips_credentials():
    assert clean("smb://bob:s3cret@nas.local/Video/a.mkv") == "smb://nas.local/Video/a.mkv"
    assert clean("rtmp://10.0.0.5:1935/live/cam") == "rtmp://10.0.0.5:1935/live/cam"


def test_display_name_never_leaks_password(links):
    assert links.display_name("ftp://bob:s3cret@127.0.0.1/movies/My%20Film.mkv") == "My Film.mkv"
    assert "s3cret" not in links.display_name("rtsp://bob:s3cret@127.0.0.1/")


@pytest.mark.parametrize("url,kind", [
    ("smb://u:p@h/share/", "dir"), ("smb://u:p@h/share/film.mkv", "video"),
    ("smb://u:p@h/share/song.flac", "audio"), ("sftp://u@h/movies", "dir"),
    ("ftp://h/a/b.mp4", "video"), ("rtmp://h/live/x", "video"), ("udp://239.1.1.1:5000", "video"),
    ("http://h/files/", "dir"), ("http://h/a.mp3", "audio"),
])
def test_kind_of(links, url, kind):
    assert links.kind_of(url) == kind


def test_validate_rejects_unknown_and_local_schemes(links):
    for bad in ("file:///etc/passwd", "gopher://127.0.0.1/", "javascript:alert(1)", "nonsense"):
        with pytest.raises(SourceError):
            links.validate(bad)


def test_validate_blocks_link_local_and_allows_multicast_for_udp(links):
    with pytest.raises(SourceError):
        links.validate("rtmp://169.254.169.254/live")
    links.validate("udp://239.1.1.1:5000")           # IPTV multicast is allowed
    with pytest.raises(SourceError):
        links.validate("rtsp://239.1.1.1/stream")    # but only for udp/rtp/srt


def test_live_link_resolves_as_native_live(links):
    ref = links.resolve(enc("rtmp://127.0.0.1:1935/live/cam"))
    assert ref.native and ref.live and ref.url.startswith("rtmp://") and ref.kind == "video"


def test_smb_link_needs_share(links):
    with pytest.raises(SourceError):
        links.browse(enc("smb://127.0.0.1/"))


def test_smb_backend_maps_url_to_share_and_path(links):
    backend, rel, prefix = links._backend("smb://bob:pw@127.0.0.1/Video/Films/a%20b.mkv")
    assert (backend.share, backend.username, backend.password) == ("Video", "bob", "pw")
    assert rel == "Films/a b.mkv"
    assert prefix == "smb://bob:pw@127.0.0.1/Video"


def test_ftp_resolve_is_native_with_encoded_credentials():
    from hush.sources.ftp import FTPSource
    src = FTPSource({"id": "x", "host": "127.0.0.1", "username": "a b", "password": "p@ss"})
    assert src._full("x/y.mkv") == "/x/y.mkv"
    with pytest.raises(SourceError):
        src._full("../etc")


def test_network_scan_finds_a_listening_service(monkeypatch):
    import socket
    from hush import discover
    srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen()
    port = srv.getsockname()[1]
    monkeypatch.setattr(discover, "SERVICES", {port: ("smb", "SMB share")})
    monkeypatch.setattr(discover, "local_network", lambda: __import__("ipaddress").ip_network("127.0.0.0/30"))
    r = discover.scan(timeout=0.3)
    srv.close()
    assert r["servers"] and r["servers"][0]["host"] == "127.0.0.1"
    assert r["servers"][0]["services"][0]["type"] == "smb"


def test_change_password(tmp_path):
    from fastapi.testclient import TestClient
    from hush.app import create_app
    from hush.config import Config
    cfg = Config(password="oldpassword", secret_key="k" * 32, data_dir=tmp_path)
    c = TestClient(create_app(cfg))
    assert c.post("/api/login", json={"password": "oldpassword"}).status_code == 200
    assert c.post("/api/password", json={"current": "nope", "new": "newpassword1"}).status_code == 403
    assert c.post("/api/password", json={"current": "oldpassword", "new": ""}).status_code == 400
    assert c.post("/api/password", json={"current": "oldpassword", "new": "newpassword1"}).status_code == 200
    assert c.get("/api/sources").status_code == 200                      # this browser stays signed in
    fresh = TestClient(create_app(cfg))                                 # restart: saved hash is used
    assert fresh.post("/api/login", json={"password": "oldpassword"}).status_code == 401
    assert fresh.post("/api/login", json={"password": "newpassword1"}).status_code == 200


def test_scan_tree_queues_unscanned_titles_once(tmp_path):
    from fastapi.testclient import TestClient
    from hush.app import create_app
    from hush.config import Config
    lib = tmp_path / "lib"; (lib / "Show" / "S1").mkdir(parents=True)
    for rel in ("a.mkv", "Show/S1/e1.mp4", "Show/S1/e2.mp4", "movie-sample.mkv", "notes.txt"):
        (lib / rel).write_bytes(b"x")
    cfg = Config(password="", secret_key="k" * 32, data_dir=tmp_path / "d",
                 sources=[{"id": "lib", "type": "local", "path": str(lib)}])
    cfg.data_dir.mkdir()
    app = create_app(cfg)
    c = TestClient(app)
    assert c.post("/api/scan-folder", json={"source_id": "lib"}).json() == {"queued": 3, "skipped": 0}
    assert c.post("/api/scan-folder", json={"source_id": "lib"}).json() == {"queued": 0, "skipped": 3}


def _lib_app(tmp_path):
    from fastapi.testclient import TestClient
    from hush.app import create_app
    from hush.config import Config
    lib = tmp_path / "lib"; lib.mkdir(exist_ok=True)
    for n in ("a.mkv", "b.mkv"):
        (lib / n).write_bytes(b"x")
    cfg = Config(password="", secret_key="k" * 32, data_dir=tmp_path / "d",
                 sources=[{"id": "lib", "type": "local", "path": str(lib)}])
    cfg.data_dir.mkdir(exist_ok=True)
    app = create_app(cfg)
    return app, TestClient(app), cfg


def test_pause_resume_state_survives_restart(tmp_path):
    app, c, cfg = _lib_app(tmp_path)
    assert c.get("/api/jobs/state").json() == {"paused": False}
    assert c.post("/api/jobs/pause").json() == {"paused": True}
    from hush.app import create_app
    assert TestClientState(create_app(cfg)) is True            # still paused after a restart
    assert c.post("/api/jobs/resume").json() == {"paused": False}


def TestClientState(app):
    from fastapi.testclient import TestClient
    return TestClient(app).get("/api/jobs/state").json()["paused"]


def test_stop_all_retry_and_restart(tmp_path):
    app, c, _ = _lib_app(tmp_path)
    assert c.post("/api/scan-folder", json={"source_id": "lib"}).json()["queued"] == 2
    assert c.post("/api/jobs/stop-all").json() == {"stopped": 2}
    assert {j["status"] for j in c.get("/api/jobs").json()} == {"cancelled"}
    assert c.post("/api/jobs/retry-failed").json() == {"queued": 2}
    first = c.get("/api/jobs").json()[0]
    new = c.post(f"/api/jobs/{first['id']}/restart").json()
    assert new["status"] == "queued" and new["id"] != first["id"]
    assert c.post("/api/jobs/nope/restart").status_code == 404


def test_interrupted_jobs_are_requeued_on_startup(tmp_path):
    from hush.app import create_app
    app, c, cfg = _lib_app(tmp_path)
    c.post("/api/scan-folder", json={"source_id": "lib"})
    ids = {j["id"] for j in c.get("/api/jobs").json()}
    app.state.db.update_job(next(iter(ids)), status="running", progress=0.5)   # as if killed mid-scan
    again = create_app(cfg)
    assert set(again.state.analyzer._resume) == ids
    assert {j["status"] for j in again.state.db.list_jobs()} == {"queued"}


IPTV = """#EXTM3U
#EXTINF:-1 tvg-id="a" group-title="News, World",BBC One
rtmp://127.0.0.1/live/bbc
#EXTINF:-1 group-title="Sport",Match 1
http://127.0.0.1/stream/match1.m3u8
#EXTINF:-1,Loose Movie
http://127.0.0.1/films/loose.mp4
#EXTINF:-1 group-title="Sport",Sport Two
udp://239.1.1.1:5000
"""
HLS = "#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:4\n#EXTINF:4,\nseg0.ts\n#EXT-X-ENDLIST\n"


def test_playlist_parse_titles_groups_and_pls():
    from hush.sources import playlist
    items = playlist.parse(IPTV)
    assert [(i["title"], i["group"]) for i in items] == [
        ("BBC One", "News, World"), ("Match 1", "Sport"), ("Loose Movie", ""), ("Sport Two", "Sport")]
    assert playlist.is_hls(HLS) and not playlist.is_hls(IPTV)
    pls = "[playlist]\nFile1=http://h/a.mp3\nTitle1=Song A\nFile2=http://h/b.mp3\nNumberOfEntries=2\n"
    assert [(i["title"], i["url"]) for i in playlist.parse(pls)] == [("Song A", "http://h/a.mp3"), ("", "http://h/b.mp3")]


def test_playlist_url_browses_with_groups_and_hls_plays(tmp_path):
    import functools, http.server, threading
    from hush.sources.base import dec, enc
    (tmp_path / "tv.m3u").write_text(IPTV)
    (tmp_path / "live.m3u8").write_text(HLS)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        L = LinkSource({"id": "url", "type": "link"})
        assert L.kind_of(f"{base}/tv.m3u") == "dir"          # a list
        assert L.kind_of(f"{base}/live.m3u8") == "video"     # an HLS stream: just play it
        root = L.browse(enc(f"{base}/tv.m3u"))
        assert sorted(e.name for e in root if e.kind == "dir") == ["News, World", "Sport"]
        assert [e.name for e in root if e.kind != "dir"] == ["Loose Movie"]
        sport = L.browse(next(e.id for e in root if e.name == "Sport"))
        assert [(e.name, e.meta.get("live", False)) for e in sport] == [("Match 1", True), ("Sport Two", True)]
        news = L.browse(next(e.id for e in root if e.name == "News, World"))
        assert dec(news[0].id).startswith("rtmp://")
        with pytest.raises(SourceError):
            L.browse(enc(f"{base}/live.m3u8"))
    finally:
        srv.shutdown()


def test_local_playlist_opens_as_folder(tmp_path):
    from hush.sources.local import LocalSource
    lib = tmp_path / "lib"; lib.mkdir()
    (lib / "a.mkv").write_bytes(b"x")
    (lib / "list.m3u").write_text("#EXTINF:-1,Film A\na.mkv\n#EXTINF:-1,Stream\nrtmp://127.0.0.1/live/x\nmissing.mkv\n")
    src = LocalSource({"id": "lib", "type": "local", "path": str(lib)})
    top = {e.name: e for e in src.browse()}
    assert top["list.m3u"].kind == "dir" and top["a.mkv"].kind == "video"
    items = src.browse(top["list.m3u"].id)
    assert [(e.name, e.source) for e in items] == [("Film A", None), ("Stream", "url")]
    assert items[1].to_dict("lib")["source_id"] == "url"


def test_more_media_types_are_recognised():
    from hush.sources.base import classify
    for name, kind in [("a.rmvb", "video"), ("a.asf", "video"), ("a.ac3", "audio"), ("a.dsf", "audio"), ("a.txt", None)]:
        assert classify(name) == kind


def _wait_task(c, tid):
    import time
    for _ in range(100):
        t = next(t for t in c.get("/api/tasks").json()["tasks"] if t["id"] == tid)
        if not t["running"]:
            return t
        time.sleep(0.05)
    raise AssertionError("task did not finish")


def test_library_refresh_task(tmp_path):
    app, c, _ = _lib_app(tmp_path)
    t = next(t for t in c.get("/api/tasks").json()["tasks"] if t["id"] == "refresh")
    assert t["enabled"] is False and t["sources"] == []             # nothing runs until you choose
    assert c.post("/api/tasks/refresh/run").json() == {"started": True}
    assert "No sources" in _wait_task(c, "refresh")["last_result"]

    r = c.put("/api/tasks/refresh", json={"sources": ["lib", "bogus"], "scan_new": True, "enabled": True,
                                          "interval_hours": 3}).json()
    t = next(t for t in r["tasks"] if t["id"] == "refresh")
    assert t["sources"] == ["lib"] and t["enabled"] and t["interval_hours"] == 3 and t["next_run"]

    c.post("/api/tasks/refresh/run")
    t = _wait_task(c, "refresh")
    assert t["last_status"] == "ok" and "2 titles, 2 new, 0 removed, 2 scans queued" in t["last_result"]
    assert c.get("/api/tasks").json()["library"] == {"titles": 2, "scanned": 0}

    (tmp_path / "lib" / "a.mkv").unlink()                          # a title disappears from the source
    c.post("/api/tasks/refresh/run")
    assert "1 titles, 0 new, 1 removed" in _wait_task(c, "refresh")["last_result"]


def test_task_validation_and_cleanup(tmp_path):
    app, c, cfg = _lib_app(tmp_path)
    assert c.put("/api/tasks/refresh", json={"interval_hours": 0.01}).status_code == 400
    assert c.put("/api/tasks/nope", json={}).status_code == 404
    assert c.post("/api/tasks/nope/run").status_code == 404
    import os, time
    cfg.cache_dir.mkdir(exist_ok=True)
    old = cfg.cache_dir / "dead.wav"; old.write_bytes(b"x")
    os.utime(old, (time.time() - 7200,) * 2)
    fresh = cfg.cache_dir / "new.wav"; fresh.write_bytes(b"x")
    c.post("/api/tasks/cleanup/run")
    assert "1 leftover files" in _wait_task(c, "cleanup")["last_result"]
    assert not old.exists() and fresh.exists()


def test_config_auto_scan_seeds_the_refresh_task(tmp_path):
    from fastapi.testclient import TestClient
    from hush.app import create_app
    from hush.config import AnalysisConfig, Config
    lib = tmp_path / "lib"; lib.mkdir()
    cfg = Config(password="", secret_key="k" * 32, data_dir=tmp_path / "d",
                 analysis=AnalysisConfig(auto_scan=["lib"], auto_scan_hours=4),
                 sources=[{"id": "lib", "type": "local", "path": str(lib)}])
    cfg.data_dir.mkdir()
    t = next(t for t in TestClient(create_app(cfg)).get("/api/tasks").json()["tasks"] if t["id"] == "refresh")
    assert t["enabled"] and t["sources"] == ["lib"] and t["interval_hours"] == 4


def test_manual_scans_go_ahead_of_bulk_and_scan_next(tmp_path):
    app, c, _ = _lib_app(tmp_path)
    (tmp_path / "lib" / "c.mkv").write_bytes(b"x")
    c.post("/api/scan-folder", json={"source_id": "lib"})                 # bulk: a, b, c
    jobs = {j["title"]: j["id"] for j in c.get("/api/jobs").json()}
    manual = c.post("/api/analyze", json={"source_id": "lib", "item_id": __import__("hush.sources.base", fromlist=["enc"]).enc("0:a.mkv"),
                                          "title": "a.mkv"}).json()
    assert manual["id"] == jobs["a.mkv"]                                   # already queued: not duplicated
    assert c.post(f"/api/jobs/{jobs['c.mkv']}/next").json()["status"] == "queued"
    assert c.post("/api/jobs/nope/next").status_code == 404
    order = []
    q = app.state.analyzer.q
    while not q.empty():
        order.append(q.get()[2])
    assert order[0] == jobs["c.mkv"]                                       # moved to the front
    assert set(order) == set(jobs.values()) | {jobs["c.mkv"]}


def test_notifications_send_when_scans_finish_and_tasks_fail(tmp_path):
    import http.server, json, threading, time
    got = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            got.append((self.headers.get("Title"), self.rfile.read(int(self.headers["Content-Length"])).decode()))
            self.send_response(200); self.end_headers()
        def log_message(self, *a): pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        app, c, _ = _lib_app(tmp_path)
        url = f"http://127.0.0.1:{srv.server_address[1]}/hush"
        assert c.put("/api/notifications", json={"url": "ftp://x/y"}).status_code == 400
        assert c.put("/api/notifications", json={"url": url}).json()["url"] == url
        assert c.post("/api/notifications/test").status_code == 200
        an = app.state.analyzer
        db = app.state.db
        jid = "j1"
        db.create_job({"id": jid, "media_key": "k", "source_id": "lib", "item_id": "i", "title": "t"})
        db.update_job(jid, status="done")
        an._after_job(jid)                                                  # queue is empty: batch reported
        for _ in range(50):
            if len(got) >= 2:
                break
            time.sleep(0.05)
        assert got[0] == ("Hush", "This is a test notification.")
        assert got[1] == ("Hush: scans finished", "1 scanned")
        c.put("/api/notifications", json={"on_scans_done": False})
        db.update_job(jid, status="error")
        an._after_job(jid)
        time.sleep(0.3)
        assert len(got) == 2                                                # switched off: nothing sent
    finally:
        srv.shutdown()


def test_a_source_that_hangs_does_not_block_the_refresh(tmp_path, monkeypatch):
    import threading, time
    from hush import tasks as tasks_mod
    from hush.sources.base import Source
    app, c, _ = _lib_app(tmp_path)

    class Hung(Source):
        type = "hung"
        def browse(self, d=""):
            threading.Event().wait(30)       # a NAS that never answers
            return []

    app.state.tasks.registry._sources["dead"] = Hung({"id": "dead", "name": "Dead NAS"})
    monkeypatch.setattr(tasks_mod, "SOURCE_TIMEOUT", 0.5)
    started = time.time()
    summary, new = app.state.tasks._index(["dead", "lib"], False)
    assert time.time() - started < 5
    assert "2 titles" in summary and "1 folders could not be opened" in summary


def test_saved_web_source_opens_playlists_as_lists(tmp_path):
    """The sources people add under "Web folder or links" must treat .m3u/.m3u8 lists like Play a link does."""
    import functools, http.server, threading
    from hush.sources import TYPES
    from hush.sources.base import enc
    (tmp_path / "iptv.m3u").write_text(IPTV)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}/iptv.m3u"
        src = TYPES["http"]({"id": "tv", "type": "http", "name": "TV", "urls": [{"name": "IPTV", "url": url}]})
        assert src.info()["type"] == "http"
        top = src.browse()
        assert [(e.name, e.kind) for e in top] == [("IPTV", "dir")]          # a list, not a video
        groups = src.browse(top[0].id)
        assert sorted(e.name for e in groups if e.kind == "dir") == ["News, World", "Sport"]
    finally:
        srv.shutdown()


def test_ten_bit_video_is_re_encoded_not_copied():
    from hush.media import ProbeResult, Stream, choose_mode
    from hush.sources.base import MediaRef
    ref = MediaRef(title="t", kind="video", path="/x/a.mkv", name="a.mkv")
    def probe(codec, pix):
        return ProbeResult(duration=60, format_names=("matroska",), video=[Stream(0, "video", codec, pix_fmt=pix)],
                           audio=[Stream(1, "audio", "aac")])
    assert choose_mode(ref, probe("h264", "yuv420p")) == "remux"          # 8-bit H.264 is copied
    assert choose_mode(ref, probe("h264", "yuv420p10le")) == "transcode"  # 10-bit H.264: browsers cannot decode it
    assert choose_mode(ref, probe("h264", "yuv422p")) == "transcode"
    assert choose_mode(ref, probe("hevc", "yuv420p10le")) == "transcode"
    mp4 = MediaRef(title="t", kind="video", path="/x/a.mp4", name="a.mp4")
    assert choose_mode(mp4, ProbeResult(60, ("mov", "mp4"), [Stream(0, "video", "h264", pix_fmt="yuv420p")], [Stream(1, "audio", "aac")])) == "direct"
    assert choose_mode(mp4, ProbeResult(60, ("mov", "mp4"), [Stream(0, "video", "h264", pix_fmt="yuv420p10le")], [Stream(1, "audio", "aac")])) == "transcode"
