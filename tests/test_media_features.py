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
    monkeypatch.setattr(art, "_scale", lambda ffmpeg, src, dst, extra_in=None: dst.write_bytes(b"ok") or True)

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
