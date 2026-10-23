from types import SimpleNamespace

import httpx

from hush import hw, media, stream
from hush.library.providers import CinemetaProvider, Chain
from hush.media import ProbeResult, Stream


def ref(live=False, ext=".mkv"):
    return SimpleNamespace(live=live, path="/x/a" + ext, native=False, url=None, headers=None, ext=ext)


def probe_of(codec, pix="yuv420p"):
    return ProbeResult(10.0, ("matroska",), [Stream(0, "video", codec, pix_fmt=pix)], [Stream(1, "audio", "aac", channels=2)])


def test_hevc_is_copied_only_when_the_screen_can_play_it():
    assert media.choose_mode(ref(), probe_of("hevc")) == "transcode"
    assert media.choose_mode(ref(), probe_of("hevc"), hevc=1) == "remux"
    assert media.choose_mode(ref(), probe_of("hevc", "yuv420p10le"), hevc=1) == "transcode"
    assert media.choose_mode(ref(), probe_of("hevc", "yuv420p10le"), hevc=2) == "remux"


def test_remuxed_hevc_is_tagged_for_browsers():
    cfg = SimpleNamespace(ffmpeg="ffmpeg", hwaccel="", video_encoder="libx264")
    cmd, _ = stream.build_ffmpeg_cmd(cfg, ref(), "s", "i", "remux", vcodec="hevc")
    assert "hvc1" in cmd
    cmd, _ = stream.build_ffmpeg_cmd(cfg, ref(), "s", "i", "remux", vcodec="h264")
    assert "hvc1" not in cmd


def test_gpu_encoders_build_their_own_arguments():
    nv = SimpleNamespace(ffmpeg="ffmpeg", hwaccel="", video_encoder="h264_nvenc")
    cmd, _ = stream.build_ffmpeg_cmd(nv, ref(), "s", "i", "transcode")
    assert "h264_nvenc" in cmd and "-cq" in cmd
    va = SimpleNamespace(ffmpeg="ffmpeg", hwaccel="", video_encoder="h264_vaapi")
    cmd, _ = stream.build_ffmpeg_cmd(va, ref(), "s", "i", "transcode")
    assert "-vaapi_device" in cmd and any("hwupload" in c for c in cmd)


def test_auto_falls_back_to_the_cpu(monkeypatch):
    monkeypatch.setattr(hw, "detect", lambda ffmpeg="ffmpeg": {"encoder": "libx264", "device": None, "gpu": ""})
    assert hw.encoder_for(SimpleNamespace(video_encoder="auto", ffmpeg="ffmpeg"))["encoder"] == "libx264"


def test_probe_survives_a_save_and_load():
    import dataclasses
    p = probe_of("h264")
    assert ProbeResult.from_saved(dataclasses.asdict(p)) == p


def test_cinemeta_finds_a_poster_and_episodes():
    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if "/catalog/movie/top/search=" in path:
            return httpx.Response(200, json={"metas": [{"imdb_id": "tt1", "name": "Crime 101", "releaseInfo": "2026",
                                                        "poster": "https://images.metahub.space/poster/small/tt1/img"}]})
        if path.startswith("/meta/movie/"):
            return httpx.Response(200, json={"meta": {"imdb_id": "tt1", "name": "Crime 101", "year": "2026", "runtime": "141 min",
                                                      "description": "A heist.", "genres": ["Crime"], "imdbRating": "6.8",
                                                      "poster": "https://images.metahub.space/poster/small/tt1/img"}})
        if path.startswith("/meta/series/"):
            return httpx.Response(200, json={"meta": {"videos": [{"season": 1, "episode": 2, "name": "Two", "overview": "x",
                                                                  "thumbnail": "https://episodes.metahub.space/tt2/1/2/w780.jpg"}]}})
        return httpx.Response(404)
    prov = CinemetaProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    hit = prov.movie("Crime 101", 2026)
    assert hit["poster_url"].endswith("/poster/medium/tt1/img") and hit["runtime"] == 141 and hit["ids"] == {"imdb": "tt1"}
    assert prov.episodes("tt2", 1)[(1, 2)]["title"] == "Two"
    assert Chain(prov)._owner("tt1") is prov


def test_guide_matches_channels_by_id_url_and_name_and_finds_now_and_next(tmp_path):
    import io
    from datetime import datetime, timedelta, timezone
    from hush import epg
    from hush.db import DB
    now = datetime.now(timezone.utc)
    f = lambda d: d.strftime("%Y%m%d%H%M%S +0000")  # noqa: E731
    prog = lambda ch, a, b, t: f'<programme start="{f(now + a)}" stop="{f(now + b)}" channel="{ch}"><title>{t}</title></programme>'  # noqa: E731
    xml = ('<tv><channel id="ABC.us"><display-name>ABC</display-name></channel>'
           '<channel id="pluto1234567890"><display-name>Pluto Movies</display-name></channel>'
           '<channel id="x9"><display-name>Cool Channel HD</display-name></channel>'
           '<channel id="nomatch"><display-name>Nothing</display-name></channel>'
           + prog("ABC.us", timedelta(minutes=-30), timedelta(minutes=30), "News") + prog("ABC.us", timedelta(minutes=30), timedelta(hours=1), "Weather")
           + prog("pluto1234567890", timedelta(minutes=-5), timedelta(hours=1), "Film") + prog("x9", timedelta(0), timedelta(hours=1), "Show")
           + prog("nomatch", timedelta(0), timedelta(hours=1), "Other") + "</tv>")
    db = DB(tmp_path / "g.db")
    db.replace_channels("pl", [("k1", "One", ";", "", "http://x/1", "i1", "ABC.us@SD"),
                               ("k2", "Two", ";", "", "http://jmp2.uk/plu-pluto1234567890.m3u8", "i2", ""),
                               ("k3", "Cool Channel", ";", "", "http://x/3", "i3", "")])
    rows, mapping = epg.parse(io.BytesIO(xml.encode()), epg.Matcher(db._all("SELECT chan_key, name, url, tvg_id FROM channels")), tag="0:")
    assert mapping == {"k1": "0:ABC.us", "k2": "0:pluto1234567890", "k3": "0:x9"}
    assert "Other" not in [r[3] for r in rows]
    db.replace_programmes(rows, mapping)
    got = db.epg_now_next(["k1", "k2", "k3"])
    assert got["k1"]["now"]["title"] == "News" and got["k1"]["next"]["title"] == "Weather"
    assert got["k2"]["now"]["title"] == "Film" and got["k3"]["now"]["title"] == "Show"


def test_playlist_header_advertises_its_guide():
    from hush.sources import playlist
    assert playlist.epg_urls('#EXTM3U url-tvg="https://e.com/g.xml.gz,https://e.com/h.xml"\n#EXTINF:-1,A\nhttp://x') == [
        "https://e.com/g.xml.gz", "https://e.com/h.xml"]


def test_artwork_follows_redirects_only_between_trusted_hosts(tmp_path, monkeypatch):
    from hush.library import art
    monkeypatch.setattr(art, "_scale", lambda ffmpeg, src, dst, extra_in=None, width=art.WIDTH: dst.write_bytes(b"ok") or True)

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/a.jpg":
            return httpx.Response(302, headers={"location": "https://static.tvmaze.com/b.jpg"})
        if req.url.path == "/evil.jpg":
            return httpx.Response(302, headers={"location": "https://evil.example/x.jpg"})
        return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=b"\xff\xd8")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert art.from_url("ffmpeg", "https://static.tvmaze.com/a.jpg", tmp_path / "x.jpg", client)
    assert not art.from_url("ffmpeg", "https://static.tvmaze.com/evil.jpg", tmp_path / "y.jpg", client)


def test_upcoming_episodes_are_kept_for_library_shows(tmp_path):
    from datetime import datetime, timedelta, timezone
    from hush import upcoming
    from hush.db import DB
    soon = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/lookup/shows":
            return httpx.Response(200, json={"id": 77})
        if req.url.path == "/shows/77/episodes":
            return httpx.Response(200, json=[
                {"season": 1, "number": 1, "name": "Old", "airstamp": old, "summary": "<p>x</p>", "runtime": 45},
                {"season": 1, "number": 2, "name": "Soon", "airstamp": soon, "summary": "<p>Next <b>one</b></p>", "runtime": 45}])
        return httpx.Response(404)
    db = DB(tmp_path / "u.db")
    db.save_show({"show_key": "sk", "title": "Show", "year": 2026, "overview": "", "genres": [], "rating": None,
                  "ids": {"imdb": "tt1"}, "provider": "nfo", "art": 0})
    msg = upcoming.refresh(db, httpx.Client(transport=httpx.MockTransport(handler)))
    got = db.list_upcoming()
    assert "1 upcoming" in msg and [g["title"] for g in got] == ["Soon"] and got[0]["overview"] == "Next one"
    assert db.get_show("sk")["ids"]["tvmaze"] == "77"


def fake_qbit(torrents, calls):
    def handler(req: httpx.Request) -> httpx.Response:
        calls.append((req.method, req.url.path))
        p = req.url.path
        if p == "/api/v2/auth/login":
            ok = b"username=u" in req.content and b"password=pw" in req.content
            return httpx.Response(200, text="Ok." if ok else "Fails.")
        if p == "/api/v2/app/version":
            return httpx.Response(200, text="v5.0.0")
        if p == "/api/v2/torrents/info":
            return httpx.Response(200, json=torrents)
        if p == "/api/v2/torrents/stop":
            return httpx.Response(200)
        if p == "/api/v2/torrents/pause":
            return httpx.Response(404)
        if p == "/api/v2/rss/items":
            return httpx.Response(200, json={"ShowRSS": {"url": "https://x/feed", "title": "My shows", "articles": [
                {"title": "Show S01E02", "date": "2026-10-18T10:00:00"}, {"title": "Show S01E01", "date": "2026-10-11T10:00:00"}]}})
        if p == "/api/v2/rss/rules":
            return httpx.Response(200, json={"Show": {"enabled": True, "mustContain": "Show", "affectedFeeds": ["https://x/feed"], "lastMatch": "x"}})
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def test_qbit_5_2_login_answers_204_with_a_cookie(tmp_path):
    from hush.db import DB
    from hush.qbit import Qbit, QbitError

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/v2/auth/login":
            good = b"password=pw" in req.content
            return httpx.Response(204, headers={"set-cookie": "QBT_SID_1=abc; path=/"}) if good else httpx.Response(401, text="Fails.")
        return httpx.Response(200, text="v5.2.4")
    qb = Qbit(DB(tmp_path / "q2.db"), transport=httpx.MockTransport(handler))
    qb.update({"url": "http://qb:1", "username": "u", "password": "pw"})
    assert qb.version() == "v5.2.4"
    qb.update({"password": "bad"})
    try:
        qb.version()
        assert False
    except QbitError:
        pass


def test_qbit_reads_downloads_and_rss_and_notices_finished_ones(tmp_path):
    from hush.db import DB
    from hush.qbit import Qbit, QbitError
    db = DB(tmp_path / "q.db")
    torrents = [{"hash": "aa", "name": "One", "progress": 1, "state": "stalledUP", "size": 10},
                {"hash": "bb", "name": "Two", "progress": 0.4, "state": "downloading", "size": 10, "dlspeed": 5}]
    calls, finished = [], []
    qb = Qbit(db, finished.extend, transport=fake_qbit(torrents, calls))
    qb.update({"url": "http://qb:8080/", "username": "u", "password": "wrong"})
    try:
        qb.version()
        assert False, "a wrong password must be refused"
    except QbitError:
        pass
    qb.update({"password": "pw"})
    assert qb.version() == "v5.0.0" and qb.public()["has_password"] and "password" not in qb.public()
    got = qb.torrents()
    assert [(t["name"], t["done"]) for t in got] == [("One", True), ("Two", False)]
    assert qb.check_finished() == []                       # first look: already-finished downloads are not news
    torrents[1].update(progress=1, state="uploading")
    assert qb.check_finished() == ["Two"] and finished == ["Two"]
    qb.act("bb", "pause")                                  # falls back from stop to pause on older versions, or stops on 5
    assert ("POST", "/api/v2/torrents/stop") in calls
    rss = qb.rss()
    assert rss["feeds"][0]["articles"][0]["title"] == "Show S01E02" and rss["rules"][0]["name"] == "Show"


def test_qbit_adds_feed_items_by_id_and_checks_links(tmp_path):
    from hush.db import DB
    from hush.qbit import Qbit, QbitError
    sent = []

    def handler(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p == "/api/v2/auth/login":
            return httpx.Response(200, text="Ok.")
        if p == "/api/v2/rss/items":
            return httpx.Response(200, json={"Feed": {"title": "F", "articles": [
                {"id": "a1", "title": "Show S01E01", "date": "2026-10-18T10:00:00", "torrentURL": "magnet:?xt=urn:btih:" + "a" * 40}]}})
        if p == "/api/v2/torrents/add":
            sent.append(req.content.decode())
            return httpx.Response(200, text="Ok.")
        return httpx.Response(404)
    qb = Qbit(DB(tmp_path / "q3.db"), transport=httpx.MockTransport(handler))
    qb.update({"url": "http://qb:1", "username": "u", "password": "p"})
    assert qb.add_from_feed("Feed", "a1") == "Show S01E01" and "urls=magnet" in sent[0]
    assert Qbit.btih("magnet:?xt=urn:btih:" + "A" * 40) == "a" * 40
    for bad in ("file:///etc/passwd", "ftp://x/y", "just words"):
        try:
            qb.add(bad)
            assert False, bad
        except QbitError:
            pass
    try:
        qb.add_from_feed("Feed", "zzz")
        assert False
    except QbitError:
        pass


def test_qbit_adds_into_a_category_or_folder_and_rejects_unknown_ones(tmp_path):
    from hush.db import DB
    from hush.qbit import Qbit, QbitError
    sent = []

    def handler(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p == "/api/v2/auth/login":
            return httpx.Response(200, text="Ok.")
        if p == "/api/v2/torrents/categories":
            return httpx.Response(200, json={"TV": {"name": "TV", "savePath": "/data/tv"}, "Movies": {"name": "Movies", "savePath": ""}})
        if p == "/api/v2/app/defaultSavePath":
            return httpx.Response(200, text="/downloads")
        if p in ("/api/v2/torrents/add", "/api/v2/torrents/setLocation", "/api/v2/torrents/setCategory"):
            sent.append((p, req.content.decode()))
            return httpx.Response(200, text="Ok.")
        return httpx.Response(404)
    qb = Qbit(DB(tmp_path / "q4.db"), transport=httpx.MockTransport(handler))
    qb.update({"url": "http://qb:1", "username": "u", "password": "p"})
    assert [c["name"] for c in qb.categories()["categories"]] == ["Movies", "TV"] and qb.categories()["default_path"] == "/downloads"
    qb.add("magnet:?xt=urn:btih:" + "b" * 40, category="TV")
    assert "category=TV" in sent[-1][1]
    qb.add("magnet:?xt=urn:btih:" + "b" * 40, save_path="/data/shows")
    assert "savepath=%2Fdata%2Fshows" in sent[-1][1]
    qb.set_category("abc123", "Movies")
    qb.set_location("abc123", "/data/movies")
    assert sent[-2][0].endswith("setCategory") and sent[-1][0].endswith("setLocation")
    for bad in ({"category": "Nope"}, {"save_path": "bad\npath"}):
        try:
            qb.add("magnet:?xt=urn:btih:" + "b" * 40, **bad)
            assert False, bad
        except QbitError:
            pass


def test_legacy_bundle_matches_app_js_and_the_page_picks_between_them():
    import hashlib
    import re
    from pathlib import Path
    web = Path(__file__).resolve().parent.parent / "hush" / "web"
    app = (web / "app.js").read_bytes()
    legacy = (web / "app.legacy.js").read_text(encoding="utf-8")
    m = re.search(r"sha256 ([0-9a-f]{64})", legacy[:300])
    assert m and m.group(1) == hashlib.sha256(app).hexdigest(), "app.legacy.js is out of date: run scripts/build-legacy.sh"
    assert not re.search(r"\w\?\.\w|\?\?[^?]", legacy.split("*/", 1)[1].replace("'?.'", "")), "newer syntax left in the legacy bundle"
    html = (web / "index.html").read_text(encoding="utf-8")
    assert 'data-modern="/static/app.js"' in html and 'data-legacy="/static/app.legacy.js"' in html


def test_the_page_stamps_both_script_versions():
    from fastapi.testclient import TestClient
    from hush.app import create_app
    from hush.config import Config
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    cfg = Config(password="", secret_key="k" * 32, data_dir=d / "d"); cfg.data_dir.mkdir(); cfg.cache_dir.mkdir()
    body = TestClient(create_app(cfg)).get("/").text
    assert 'data-modern="/static/app.js?v=' in body and 'data-legacy="/static/app.legacy.js?v=' in body


def test_weather_search_and_current(monkeypatch):
    from hush import weather

    def handler(req: httpx.Request) -> httpx.Response:
        if "geocoding" in req.url.host:
            return httpx.Response(200, json={"results": [{"name": "Austin", "admin1": "Texas", "country": "United States", "latitude": 30.27, "longitude": -97.74, "timezone": "America/Chicago"}]})
        return httpx.Response(200, json={"current": {"temperature_2m": 71.6, "weather_code": 2}, "daily": {"temperature_2m_max": [80.2], "temperature_2m_min": [60.1]}, "timezone": "America/Chicago"})
    c = httpx.Client(transport=httpx.MockTransport(handler))
    assert weather.search("Austin", c) == [{"name": "Austin", "region": "Texas", "country": "United States", "lat": 30.27, "lon": -97.74, "timezone": "America/Chicago"}]
    weather._cache.clear()
    now = weather.current(30.27, -97.74, "f", c)
    assert (now["temp"], now["text"], now["high"], now["low"], now["unit"]) == (72, "Partly cloudy", 80, 60, "°F")
    assert now["icon"] and now["days"] == [] and now["wind_unit"] == "mph"


def test_world_clocks_are_saved_and_cleaned(tmp_path):
    from fastapi.testclient import TestClient
    from hush.app import create_app
    from hush.config import Config
    cfg = Config(password="", secret_key="k" * 32, data_dir=tmp_path / "d"); cfg.data_dir.mkdir(); cfg.cache_dir.mkdir()
    c = TestClient(create_app(cfg))
    r = c.put("/api/clocks/set", json=[{"name": "Tokyo", "tz": "Asia/Tokyo"}, {"name": "Bad", "tz": "../etc"}, {"name": "", "tz": "UTC"}])
    assert r.status_code == 200 and r.json() == [{"name": "Tokyo", "tz": "Asia/Tokyo"}]
    assert c.get("/api/clocks").json() == [{"name": "Tokyo", "tz": "Asia/Tokyo"}]


def test_the_phone_remote_can_send_text():
    from hush.remote import COMMANDS
    assert "text" in COMMANDS
