"""Library: file-name parsing, NFO reading."""
import pytest

from hush.library.parse import display_title, nfo_for, parse_name, safe_name, show_nfo_for


@pytest.mark.parametrize("name,title,year", [
    ("72.Hours.2026.1080p.WEBRip.10Bit.DDP5.1.x265-NeoNoir.mkv", "72 Hours", 2026),
    ("Backrooms (2026) [1080p] [WEBRip] [5.1] [YTS.GG - YTS.BZ]", "Backrooms", 2026),
    ("Crime 101 2026 1080p WEB Line HEVC x265 BONE.mkv", "Crime 101", 2026),
    ("Enola.Holmes.3.2026.1080p.WEBRip.10Bit.DDP5.1.x265-NeoNoir.mkv", "Enola Holmes 3", 2026),
    ("Spider-Man- Brand New Day 2026.1080p.HQ Pre.Multi.AAC 2.0.x264.mkv", "Spider-Man: Brand New Day", 2026),
    ("Star.Trek.Nemesis.2002.REMASTERED.1080p.BluRay.x265-RBG.nfo", "Star Trek Nemesis", 2002),
    ("The Death Of Robin Hood (2026) [RETAIL DKSUBS] [1080p] [WEBRip] [5.1] [YTS.GG - YTS.BZ]", "The Death Of Robin Hood", 2026),
    ("www.UIndex.org    -    1000 To 1 The Cory Weissman Story (2014) 1080p WEBRip 5.1-LAMA", "1000 To 1 The Cory Weissman Story", 2014),
    ("Blade Runner 2049 (2017) 1080p.mkv", "Blade Runner 2049", 2017),
    ("Coyote Vs. Acme (2026) [1080p] [WEBRip] [5.1] [YTS.GG - YTS.BZ]", "Coyote Vs. Acme", 2026),
    ("Just A Title.mkv", "Just A Title", None),
])
def test_parse_movies(name, title, year):
    m = parse_name(name)
    assert (m["kind"], m["title"], m["year"]) == ("movie", title, year)


@pytest.mark.parametrize("name,show,year,s,e,ep", [
    ("9-1-1.S10E01.1080p.HDTV.x264-SYNCOPY[EZTVx.to].nfo", "9-1-1", None, 10, 1, ""),
    ("Collision 2026 S01E03 Profile of an Ex-Convict 1080p AMZN WEB-DL DUAL DDP5 1 H 264-RAWR[EZTVx.to].mkv",
     "Collision", 2026, 1, 3, "Profile of an Ex-Convict"),
    ("Secret Invasion (2023) - S01E02 - Promises (1080p DSNP WEB-DL x265 Silence).mkv", "Secret Invasion", 2023, 1, 2, "Promises"),
    ("Chicago.Med.S12E02.1080p.HDTV.x264-SYNCOPY[EZTVx.to].nfo", "Chicago Med", None, 12, 2, ""),
    ("Show Name 2x05 Some Title 720p.mkv", "Show Name", None, 2, 5, "Some Title"),
])
def test_parse_episodes(name, show, year, s, e, ep):
    m = parse_name(name)
    assert (m["kind"], m["title"], m["year"], m["season"], m["episode"], m["ep_title"]) == ("episode", show, year, s, e, ep)


def test_safe_name_and_display_title():
    assert safe_name("Spider-Man: Brand New Day") == "Spider-Man - Brand New Day"
    assert safe_name('What? "Now" <1>/2*') == "What Now 1-2"
    assert display_title({"title": "Heat", "year": 1995}) == "Heat (1995)" and display_title({"title": "Heat"}) == "Heat"


def test_nfo_reading(tmp_path):
    (tmp_path / "film.mkv").write_bytes(b"x")
    (tmp_path / "film.nfo").write_text('﻿<?xml version="1.0" encoding="utf-8"?>\n<movie><title>In the Grey</title>'
        '<year>2026</year><plot>A heist.</plot><genre>Action</genre><genre>Crime</genre><runtime>115</runtime>'
        '<uniqueid type="imdb">tt123</uniqueid><tmdbid>77</tmdbid></movie>')
    n = nfo_for(tmp_path / "film.mkv")
    assert (n["title"], n["year"], n["overview"], n["genres"], n["runtime"]) == ("In the Grey", 2026, "A heist.", ["Action", "Crime"], 115)
    assert n["ids"] == {"imdb": "tt123", "tmdb": "77"}
    (tmp_path / "other.mkv").write_bytes(b"x")
    assert nfo_for(tmp_path / "other.mkv") == {}
    (tmp_path / "bad.nfo").write_text("not xml at all")
    assert nfo_for(tmp_path / "bad.mkv") == {}
    sub = tmp_path / "Show" / "S1"; sub.mkdir(parents=True)
    (tmp_path / "Show" / "tvshow.nfo").write_text("<tvshow><title>The Show</title><year>2020</year></tvshow>")
    assert show_nfo_for(sub / "e1.mkv")["title"] == "The Show"


# ---- details service -------------------------------------------------------------------
import subprocess


def _ff(*a):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *a], check=True)


class FakeProvider:
    """Stands in for TMDB / TVmaze: answers from a fixed table, no network."""
    name = "fake"

    def __init__(self):
        self.calls = 0

    def movie(self, title, year):
        self.calls += 1
        if title.lower().startswith("tom clancys"):
            return {"provider": "fake", "id": "9", "title": "Tom Clancy's Jack Ryan: Ghost War", "year": 2026,
                    "overview": "Ryan returns.", "genres": ["Action"], "rating": 7.1, "runtime": 110, "ids": {"fake": "9"},
                    "poster_url": None}
        return None

    def show(self, title, year):
        self.calls += 1
        return {"provider": "fake", "id": "5", "title": "Collision", "year": 2026, "overview": "A crash.",
                "genres": ["Drama"], "rating": 8.0, "poster_url": None, "ids": {"fake": "5"}}

    def episodes(self, sid, season):
        return {(1, 1): {"title": "Business Protocol", "overview": "Day one.", "still_url": None}}


@pytest.fixture()
def lib_service(tmp_path):
    from hush.config import Config
    from hush.db import DB
    from hush.library.service import MetadataService
    from hush.sources import Registry
    root = tmp_path / "media"; (root / "Backrooms (2026) [1080p]").mkdir(parents=True)
    _ff("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=10", "-t", "3", "-pix_fmt", "yuv420p", str(root / "Backrooms (2026) [1080p]" / "Backrooms.2026.1080p.mkv"))
    (root / "Backrooms (2026) [1080p]" / "movie.nfo").write_text("<movie><title>Backrooms</title><year>2026</year><plot>Lost in rooms.</plot><genre>Horror</genre></movie>")
    _ff("-f", "lavfi", "-i", "color=c=red:size=200x300", "-frames:v", "1", str(root / "Backrooms (2026) [1080p]" / "poster.jpg"))
    _ff("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=10", "-t", "3", "-pix_fmt", "yuv420p", str(root / "Tom.Clancys.Jack.Ryan.Ghost.War.2026.Multi.WEBRIP.mkv"))
    _ff("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=10", "-t", "3", "-pix_fmt", "yuv420p",
        str(root / "Collision 2026 S01E01 Business Protocol 1080p WEB-DL.mkv"))
    cfg = Config(password="", secret_key="k" * 32, data_dir=tmp_path / "d",
                 sources=[{"id": "m", "type": "local", "path": str(root)}])
    cfg.data_dir.mkdir()
    db = DB(cfg.db_path)
    reg = Registry(cfg.sources, db)
    from hush.analysis.walk import walk
    from hush.sources import media_key
    now = __import__("time").time()
    db.record_library("m", [(media_key("m", e.id), "m", e.id, e.name) for e in walk(reg.get("m"))], now)
    return MetadataService(cfg, db, reg), db


def test_enrich_uses_nfo_poster_provider_and_thumbnails(lib_service, monkeypatch):
    svc, db = lib_service
    from hush.library import service as svc_mod
    fake = FakeProvider()
    monkeypatch.setattr(svc_mod, "pick_providers", lambda s: (fake, fake))
    monkeypatch.setattr(svc_mod.time, "sleep", lambda s: None)
    r = svc.process_library()
    assert r == {"processed": 3, "failed": 0}
    by_title = {m["title"]: m for m in db.list_movies()}
    nfo_movie = by_title["Backrooms"]
    assert nfo_movie["provider"] == "nfo" and nfo_movie["overview"] == "Lost in rooms." and nfo_movie["art"] == 1
    assert nfo_movie["genres"] == ["Horror"]
    clancy = by_title["Tom Clancy's Jack Ryan: Ghost War"]                  # the name was corrected online
    assert clancy["provider"] == "fake" and clancy["year"] == 2026 and clancy["art"] == 1   # thumbnail from the video
    assert (svc.art_dir / f"{clancy['media_key']}.jpg").stat().st_size > 0
    shows = db.list_shows()
    assert [(s["title"], s["overview"], s["episodes"]) for s in shows] == [("Collision", "A crash.", 1)]
    ep = db.episodes_of(shows[0]["show_key"])[0]
    assert (ep["season"], ep["episode"], ep["title"], ep["overview"]) == (1, 1, "Business Protocol", "Day one.")
    assert shows[0]["art"] == 1                                              # borrowed from the episode thumbnail
    assert svc.process_library() == {"processed": 0, "failed": 0}           # nothing left to do, no repeat lookups


def test_locked_choices_are_not_overwritten(lib_service, monkeypatch):
    svc, db = lib_service
    from hush.library import service as svc_mod
    monkeypatch.setattr(svc_mod, "pick_providers", lambda s: (None, None))
    svc.process_library()
    m = next(m for m in db.list_movies() if m["title"].startswith("Tom"))
    m["locked"], m["title"] = 1, "My Own Title"
    db.save_meta(m)
    row = {"source_id": m["source_id"], "item_id": m["item_id"], "media_key": m["media_key"], "title": "x"}
    assert svc.enrich(row, (None, None))["title"] == "My Own Title"


def test_library_api_and_settings(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from hush.app import create_app
    from hush.config import Config
    cfg = Config(password="", secret_key="k" * 32, data_dir=tmp_path / "d"); cfg.data_dir.mkdir()
    app = create_app(cfg); c = TestClient(app)
    assert c.get("/api/library/settings").json() == {"provider": "auto", "language": "en-US", "has_key": False}
    assert c.put("/api/library/settings", json={"provider": "tmdb"}).status_code == 400        # needs a key
    r = c.put("/api/library/settings", json={"provider": "tmdb", "tmdb_key": "abc123"}).json()
    assert r["has_key"] is True and "abc123" not in str(c.get("/api/library/settings").json())  # the key never comes back
    assert c.get("/api/library/movies").json() == [] and c.get("/api/library/shows").json() == []
    assert c.get("/api/art/nope.jpg").status_code == 404 and c.get("/api/art/..%2Fx.jpg").status_code in (404, 422)
    assert c.get("/api/library/shows/none").status_code == 404


# ---- transcripts -------------------------------------------------------------------------
def test_transcript_formats_and_masking():
    from hush.analysis.matcher import Word
    from hush.library import transcript as tr
    words = [Word(" Hello", 1.0, 1.4), Word(" there.", 1.4, 1.9), Word(" What", 5.0, 5.3), Word(" the", 5.3, 5.5),
             Word(" hell", 5.5, 5.9), Word(" is", 5.9, 6.0), Word(" that?", 6.0, 6.4)]
    srt = tr.to_srt(words)
    assert srt.startswith("1\n00:00:01,000 --> 00:00:01,900\nHello there.\n\n2\n00:00:05,000 --> 00:00:06,400\nWhat the hell is that?")
    assert tr.to_vtt(words).startswith("WEBVTT\n\n00:00:01.000 --> 00:00:01.900\nHello there.")
    assert tr.to_txt(words, "Film") == "Film\n====\n\nHello there.\n\nWhat the hell is that?\n"
    masked = tr.mask(words, [{"start": 5.5, "end": 5.9}])
    assert [w.text for w in masked][4] == " h***" and masked[0].text == " Hello"


def test_transcript_and_captions_endpoints(tmp_path):
    import json
    from fastapi.testclient import TestClient
    from hush.app import create_app
    from hush.config import Config
    from hush.sources.base import enc
    lib = tmp_path / "lib"; lib.mkdir()
    _ff("-f", "lavfi", "-i", "testsrc2=size=160x90:rate=10", "-t", "2", "-pix_fmt", "yuv420p", str(lib / "a.mkv"))
    (lib / "a.srt").write_text("1\n00:00:00,500 --> 00:00:01,500\nHi there\n")
    cfg = Config(password="", secret_key="k" * 32, data_dir=tmp_path / "d",
                 sources=[{"id": "lib", "type": "local", "path": str(lib)}])
    cfg.data_dir.mkdir(); cfg.cache_dir.mkdir()
    c = TestClient(create_app(cfg))
    item = enc("0:a.mkv")
    info = c.get(f"/api/captions/lib/{item}").json()
    assert info["transcript"] is False and info["tracks"] == [{"id": "side0", "label": "a.srt", "where": "next to the file"}]
    assert c.get(f"/api/transcript/{info['key']}.srt").status_code == 404
    (cfg.cache_dir / f"{info['key']}.words.json").write_text(json.dumps(
        {"engine": "whisper", "words": [[" What", 0.0, 0.3], [" the", 0.3, 0.5], [" hell", 0.5, 0.9]]}))
    r = c.get(f"/api/transcript/{info['key']}.srt?censor=1")
    assert r.status_code == 200 and "What the h***" in r.text and "attachment" in r.headers["content-disposition"]
    assert "hell" in c.get(f"/api/transcript/{info['key']}.txt").text
    assert c.get(f"/api/transcript/{info['key']}.exe").status_code == 404
    srt = c.get(f"/api/subtitle/lib/{item}/side0?format=srt&download=1")
    assert srt.status_code == 200 and "Hi there" in srt.text and "00:00:00,500" in srt.text


# ---- tidy renames -------------------------------------------------------------------------
@pytest.fixture()
def rename_env(tmp_path):
    from hush.config import Config
    from hush.db import DB
    from hush.library.rename import Renamer
    from hush.sources import Registry, media_key
    from hush.analysis.walk import walk
    root = tmp_path / "media"
    def touch(rel, data=b"x"):
        p = root / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data); return p
    touch("72.Hours.2026.1080p.WEBRip.x265-NeoNoir.mkv"); touch("72.Hours.2026.1080p.WEBRip.x265-NeoNoir.nfo")
    touch("72.Hours.2026.1080p.WEBRip.x265-NeoNoir.en.srt")
    touch("Uncharted (2022) [1080p] [BluRay]/Uncharted.2022.1080p.BluRay.mp4"); touch("Uncharted (2022) [1080p] [BluRay]/movie.nfo")
    touch("Uncharted (2022) [1080p] [BluRay]/poster.jpg")
    touch("Collision 2026 S01E01 Business Protocol 1080p WEB-DL.mkv"); touch("Collision 2026 S01E01 Business Protocol 1080p WEB-DL.nfo")
    touch("Secret Invasion (2023) Season 1 S01 (1080p)/Secret Invasion (2023) - S01E01 - Resurrection (1080p).mkv")
    touch("Secret Invasion (2023) Season 1 S01 (1080p)/Secret Invasion (2023) - S01E02 - Promises (1080p).mkv")
    touch("Secret Invasion (2023) Season 1 S01 (1080p)/tvshow.nfo")
    cfg = Config(password="", secret_key="k" * 32, data_dir=tmp_path / "d", sources=[{"id": "m", "type": "local", "path": str(root)}])
    cfg.data_dir.mkdir(); cfg.cache_dir.mkdir()
    db = DB(cfg.db_path); reg = Registry(cfg.sources, db)
    db.record_library("m", [(media_key("m", e.id), "m", e.id, e.name) for e in walk(reg.get("m"))], 1.0)
    from hush.library.service import MetadataService, show_key_for
    svc = MetadataService(cfg, db, reg)
    from hush.library import service as svc_mod
    svc_mod.pick_providers = lambda s: (None, None)
    svc.process_library()
    # pretend an online match fixed the names
    for m in db.list_movies():
        if m["title"].startswith("72"):
            m.update(title="72 Hours", provider="tmdb", year=2026); db.save_meta(m)
        if m["title"].startswith("Uncharted"):
            m.update(provider="tmdb"); db.save_meta(m)
    for s in db.list_shows():
        s["provider"] = "tmdb"; db.save_show(s)
    for s in db.list_shows():
        for e in db.episodes_of(s["show_key"]):
            e["provider"] = "tmdb"; db.save_meta(e)
    r = Renamer(db, reg); r.cache_dir = cfg.cache_dir; r.art_dir = svc.art_dir
    return root, db, r, cfg


def _tree(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())


def test_rename_plan_apply_and_undo(rename_env):
    root, db, r, cfg = rename_env
    before = _tree(root)
    plan = r.plan("m", layout="folders")
    assert _tree(root) == before                                            # a preview changes nothing
    labels = sorted(g["label"] for g in plan["groups"])
    assert labels == ["72 Hours (2026)", "Collision (2026) · Season 01 · 1 episode", "Secret Invasion (2023) · Season 01", "Uncharted (2022)"]
    # give a title a filter and cached transcript so we can see them follow the file
    m72 = next(m for m in db.list_movies() if m["title"] == "72 Hours")
    db.save_filter(m72["media_key"], "m", m72["item_id"], "72 Hours", 5.0, "whisper", [])
    (cfg.cache_dir / f"{m72['media_key']}.words.json").write_text("{}")

    res = r.apply("m", [g["id"] for g in plan["groups"]], layout="folders")
    assert res["renamed"] == 5 and res["failed"] == []
    assert _tree(root) == sorted([
        "72 Hours (2026)/72 Hours (2026).mkv", "72 Hours (2026)/72 Hours (2026).nfo", "72 Hours (2026)/72 Hours (2026).en.srt",
        "Uncharted (2022)/Uncharted (2022).mp4", "Uncharted (2022)/movie.nfo", "Uncharted (2022)/poster.jpg",
        "Collision (2026)/Season 01/Collision (2026) - S01E01 - Business Protocol.mkv",
        "Collision (2026)/Season 01/Collision (2026) - S01E01 - Business Protocol.nfo",
        "Secret Invasion (2023)/Season 01/Secret Invasion (2023) - S01E01 - Resurrection.mkv",
        "Secret Invasion (2023)/Season 01/Secret Invasion (2023) - S01E02 - Promises.mkv",
        "Secret Invasion (2023)/Season 01/tvshow.nfo"])
    moved = db.get_meta(next(m for m in db.list_movies() if m["title"] == "72 Hours")["media_key"])
    assert moved["item_id"] != m72["item_id"]                              # the library follows the file
    assert db.get_filter(moved["media_key"])["title"] == "72 Hours"        # and so does its filter
    assert (cfg.cache_dir / f"{moved['media_key']}.words.json").exists() and not (cfg.cache_dir / f"{m72['media_key']}.words.json").exists()
    assert r.plan("m", layout="folders")["groups"] == []                    # now it is all tidy

    undone = r.undo(res["batch"])
    assert undone["problems"] == [] and _tree(root) == before
    assert db.get_filter(m72["media_key"])["title"] == "72 Hours"          # filter back under the old key
    with pytest.raises(Exception):
        r.undo(res["batch"])


def test_rename_never_overwrites_and_skips_unmatched(rename_env):
    root, db, r, cfg = rename_env
    (root / "72 Hours (2026)").mkdir(); (root / "72 Hours (2026)" / "72 Hours (2026).mkv").write_bytes(b"other")
    plan = r.plan("m", layout="folders")
    assert "72 Hours (2026)" not in [g["label"] for g in plan["groups"]]
    assert any("already exists" in s["reason"] for s in plan["skipped"])
    m = next(m for m in db.list_movies() if m["title"] == "Uncharted")
    m["provider"] = "name"; db.save_meta(m)
    assert any("no match" in s["reason"] for s in r.plan("m", layout="folders")["skipped"])
    assert "Uncharted (2022)" in [g["label"] for g in r.plan("m", only_matched=False, layout="folders")["groups"]]


def test_rename_refuses_non_local_and_stale_plans(rename_env, tmp_path):
    root, db, r, cfg = rename_env
    from hush.library.rename import RenameError
    with pytest.raises(RenameError):
        r.apply("m", ["notaplanid"])
    r.registry._add({"id": "web", "type": "http", "name": "w"})
    with pytest.raises(RenameError):
        r.plan("web")


def test_rename_rolls_back_a_group_that_fails_halfway(rename_env, monkeypatch):
    import os
    root, db, r, cfg = rename_env
    before = _tree(root)
    real, calls = os.rename, {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("disk went away")
        return real(src, dst)

    monkeypatch.setattr(os, "rename", flaky)
    plan = r.plan("m", layout="folders")
    group = next(g for g in plan["groups"] if g["label"] == "72 Hours (2026)")      # several steps: mkdir + 3 moves
    res = r.apply("m", [group["id"]], layout="folders")
    assert res["renamed"] == 0 and res["failed"][0]["name"] == "72 Hours (2026)"
    monkeypatch.setattr(os, "rename", real)
    assert _tree(root) == before and not (root / "72 Hours (2026)").exists()       # nothing left behind
    assert db.rename_batches() == []                                                # and nothing journaled


def test_flat_layout_puts_everything_in_the_source_folder(rename_env):
    root, db, r, cfg = rename_env
    before = _tree(root)
    plan = r.plan("m")                                                   # flat is the default
    assert sorted(g["label"] for g in plan["groups"]) == [
        "72 Hours (2026)", "Collision (2026)", "Secret Invasion (2023) · 2 episodes", "Uncharted (2022) · 1 file"]
    assert _tree(root) == before
    m72 = next(m for m in db.list_movies() if m["title"] == "72 Hours")
    db.save_filter(m72["media_key"], "m", m72["item_id"], "72 Hours", 5.0, "whisper", [])
    res = r.apply("m", [g["id"] for g in plan["groups"]])
    assert res["renamed"] == 5 and res["failed"] == []
    assert _tree(root) == sorted([
        "72 Hours (2026).mkv", "72 Hours (2026).nfo", "72 Hours (2026).en.srt",
        "Uncharted (2022).mp4", "Uncharted (2022).nfo", "Uncharted (2022)-poster.jpg",
        "Collision (2026) - S01E01 - Business Protocol.mkv", "Collision (2026) - S01E01 - Business Protocol.nfo",
        "Secret Invasion (2023) - S01E01 - Resurrection.mkv", "Secret Invasion (2023) - S01E02 - Promises.mkv",
        "Secret Invasion (2023) Season 1 S01 (1080p)/tvshow.nfo"])           # leftovers stay; the media is out
    moved = next(m for m in db.list_movies() if m["title"] == "72 Hours")
    assert moved["item_id"] != m72["item_id"] and db.get_filter(moved["media_key"]) is not None
    assert not (root / "Uncharted (2022) [1080p] [BluRay]").exists()      # the emptied folder was removed
    assert r.plan("m")["groups"] == []
    assert r.undo(res["batch"])["problems"] == [] and _tree(root) == before
