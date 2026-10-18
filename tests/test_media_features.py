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


def test_guide_keeps_only_wanted_channels_and_finds_now_and_next(tmp_path):
    import io, time
    from datetime import datetime, timedelta, timezone
    from hush import epg
    from hush.db import DB
    now = datetime.now(timezone.utc)
    f = lambda d: d.strftime("%Y%m%d%H%M%S +0000")  # noqa: E731
    xml = (f'<tv><channel id="a"/><programme start="{f(now - timedelta(minutes=30))}" stop="{f(now + timedelta(minutes=30))}" channel="a">'
           f'<title>News</title></programme><programme start="{f(now + timedelta(minutes=30))}" stop="{f(now + timedelta(hours=1))}" channel="a">'
           f'<title>Weather</title></programme><programme start="{f(now)}" stop="{f(now + timedelta(hours=1))}" channel="zzz"><title>Other</title></programme></tv>')
    rows = epg.parse(io.BytesIO(xml.encode()), {"a"})
    assert [r[3] for r in rows] == ["News", "Weather"]
    db = DB(tmp_path / "g.db")
    db.replace_channels("pl", [("k1", "One", ";", "", "http://x/1", "id1", "a")])
    db.replace_programmes(rows)
    got = db.epg_now_next(["k1"])["k1"]
    assert got["now"]["title"] == "News" and got["next"]["title"] == "Weather"


def test_playlist_header_advertises_its_guide():
    from hush.sources import playlist
    assert playlist.epg_urls('#EXTM3U url-tvg="https://e.com/g.xml.gz,https://e.com/h.xml"\n#EXTINF:-1,A\nhttp://x') == [
        "https://e.com/g.xml.gz", "https://e.com/h.xml"]
