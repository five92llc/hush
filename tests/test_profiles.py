"""Profiles: names only, per-profile data, and a kids profile that only sees vetted titles."""
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from hush.app import create_app
from hush.config import Config
from hush.profiles import approved, cert_level
from hush.sources import media_key
from hush.sources.base import enc


@pytest.fixture()
def env(tmp_path):
    cfg = Config(password="", secret_key="k" * 32, data_dir=tmp_path / "d"); cfg.data_dir.mkdir(); cfg.cache_dir.mkdir()
    app = create_app(cfg)
    db = app.state.db

    def movie(name, flags=None, cert=None, scanned=True):
        key = media_key("lib", enc(name))
        db.save_meta({"media_key": key, "source_id": "lib", "item_id": enc(name), "kind": "movie", "title": name, "year": 2020,
                      "provider": "nfo", "cert": cert})
        if scanned:
            ranges = [{"id": f"{i}", "start": i, "end": i + 1, "words": ["x"], "category": cat, "context": "", "source": "auto", "enabled": True}
                      for cat, n in (flags or {}).items() for i in range(n)]
            db.save_filter(key, "lib", enc(name), name, 100.0, "whisper", ranges)
        return key

    keys = {"clean": movie("Clean Fun", cert="PG"), "mild": movie("Mild Words", {"mild": 2}), "swears": movie("Heavy Words", {"strong": 5}),
            "unscanned": movie("Never Scanned", scanned=False), "rated": movie("Grown Up Stuff", cert="R")}
    # a show: one clean episode, one flagged
    db.save_show({"show_key": "sh1", "title": "The Show", "year": 2020, "provider": "nfo", "cert": "TV-PG"})
    for n, flags in ((1, {}), (2, {"slurs": 1})):
        key = media_key("lib", enc(f"ep{n}"))
        db.save_meta({"media_key": key, "source_id": "lib", "item_id": enc(f"ep{n}"), "kind": "episode", "title": f"Ep {n}", "show_key": "sh1",
                      "season": 1, "episode": n, "provider": "nfo"})
        db.save_filter(key, "lib", enc(f"ep{n}"), f"Ep {n}", 100.0, "whisper",
                       [{"id": "a", "start": 1, "end": 2, "words": ["x"], "category": c, "context": "", "source": "auto", "enabled": True} for c in flags])
    c = TestClient(app)
    return c, db, keys


def make_kid(c, **settings):
    r = c.post("/api/profiles", json={"name": "Sam", "kids": True, "settings": settings})
    assert r.status_code == 200, r.text
    return r.json()


def as_profile(c, pid):
    assert c.post("/api/profiles/select", json={"id": pid}).status_code == 200


def test_rules_and_ratings():
    assert [cert_level(x) for x in ("Rated PG-13", "US:TV-MA", "PG", "G", "Unrated", None, "junk")] == [2, 3, 1, 0, None, None, None]
    kid = {"kids": True, "settings": {}}
    assert approved(kid, {"scanned": True, "flags": "{}", "cert": "PG"})
    assert not approved(kid, {"scanned": True, "flags": "{}", "cert": None})                # no rating: cannot be vouched for
    assert approved({"kids": True, "settings": {"allow_unrated": True}}, {"scanned": True, "flags": "{}", "cert": None})
    assert not approved(kid, {"scanned": True, "flags": '{"mild": 1}'})            # any flagged moment, by default
    assert not approved(kid, {"scanned": False})                                    # never scanned: cannot be vouched for
    assert not approved(kid, {"scanned": True, "flags": "{}", "cert": "R"})          # too mature
    assert not approved(kid, None)                                                  # not in the library
    assert approved({"kids": False}, None)                                          # grown-ups see everything
    relaxed = {"kids": True, "settings": {"block": ["strong", "sexual", "slurs", "blasphemy"], "max_cert": 2}}
    assert approved(relaxed, {"scanned": True, "flags": '{"mild": 4}', "cert": "PG-13"})   # mild language allowed here
    assert not approved(relaxed, {"scanned": True, "flags": '{"strong": 1}'})
    assert approved(kid, {"scanned": True, "flags": "{}", "cert": None, "show_cert": "TV-PG"})
    assert not approved(kid, {"scanned": True, "flags": "{}", "cert": None, "show_cert": "TV-MA"})   # a show's rating covers its episodes


def test_default_profile_and_picker(env):
    c, db, _ = env
    r = c.get("/api/profiles").json()
    assert [p["name"] for p in r["profiles"]] == ["Main"] and r["needs_pick"] is False and r["can_manage"] is True
    kid = make_kid(c)
    assert kid["kids"] and kid["settings"]["max_hits"] == 0 and kid["settings"]["allow_live"] is False
    fresh = TestClient(c.app)                                                        # a browser that has not chosen yet
    assert fresh.get("/api/profiles").json()["needs_pick"] is True                   # two profiles: it must ask
    assert c.post("/api/profiles", json={"name": "sam"}).status_code == 400          # names are unique
    assert c.post("/api/profiles", json={"name": " "}).status_code == 400


def test_kids_only_see_vetted_titles(env):
    c, db, keys = env
    adult_titles = {m["title"] for m in c.get("/api/library/movies").json()}
    assert adult_titles == {"Clean Fun", "Mild Words", "Heavy Words", "Never Scanned", "Grown Up Stuff"}
    kid = make_kid(c); as_profile(c, kid["id"])
    assert [m["title"] for m in c.get("/api/library/movies").json()] == ["Clean Fun"]               # rated PG, scanned, clean
    shows = c.get("/api/library/shows").json()
    assert [(s["title"], s["episodes"]) for s in shows] == [("The Show", 1)]          # only the clean episode counts
    eps = c.get("/api/library/shows/sh1").json()["episodes"]
    assert [e["title"] for e in eps] == ["Ep 1"]
    assert c.get(f"/api/library/title/{keys['clean']}").status_code == 200
    for hidden in ("mild", "swears", "unscanned", "rated"):
        assert c.get(f"/api/library/title/{keys[hidden]}").status_code == 404

    # the server refuses what the buttons hide, even if someone types the address
    item = enc("Heavy Words")
    for url in (f"/api/media/lib/{item}", f"/api/raw/lib/{item}", f"/api/stream/lib/{item}", f"/api/hls/start/lib/{item}",
                f"/api/filters/{keys['swears']}", f"/api/progress/{keys['swears']}"):
        r = c.get(url) if "progress" not in url else c.post(url, json={"source_id": "lib", "item_id": item, "position": 50, "duration": 100})
        assert r.status_code == 403, url
    assert c.get(f"/api/filters/{keys['clean']}").status_code in (200, 404)           # fine to read a vetted title's filter
    assert c.get(f"/api/media/lib/{enc('Clean Fun')}").status_code != 403              # and a vetted title is allowed through (the file is absent here)
    for url in ("/api/tasks", "/api/jobs", "/api/notifications", "/api/rename/plan?source_id=lib", "/api/live/channels", "/api/library/settings",
                "/api/transcript/abc.srt", "/api/browse/lib", "/api/open-url"):
        assert c.get(url).status_code == 403, url
    assert c.get("/api/sources").json() == []                                        # no folders to browse
    assert c.post("/api/sources", json={"type": "local", "path": "/"}).status_code == 403
    assert c.post("/api/analyze", json={"source_id": "lib", "item_id": item}).status_code == 403
    assert c.post("/api/profiles", json={"name": "Hacker"}).status_code == 403       # kids cannot add profiles
    assert c.put("/api/filters/x", json={}).status_code == 403
    assert c.get("/api/art/" + keys["swears"] + ".jpg").status_code == 403
    assert c.get("/api/progress/recent").json() == []


def test_kids_settings_loosen_and_tighten(env):
    c, db, keys = env
    kid = make_kid(c, block=["strong", "sexual", "slurs", "blasphemy"], max_cert=5, hide_unscanned=False, allow_unrated=True)   # mild OK, any rating, unscanned OK
    as_profile(c, kid["id"])
    assert {m["title"] for m in c.get("/api/library/movies").json()} == {"Clean Fun", "Mild Words", "Never Scanned", "Grown Up Stuff"}
    # a parent tightens it again
    main = next(p for p in c.get("/api/profiles").json()["profiles"] if not p["kids"])
    as_profile(c, main["id"])
    assert c.put(f"/api/profiles/{kid['id']}", json={"settings": {"block": ["strong", "mild", "sexual", "slurs", "blasphemy"], "max_cert": 1, "hide_unscanned": True}}).status_code == 200
    as_profile(c, kid["id"])
    assert [m["title"] for m in c.get("/api/library/movies").json()] == ["Clean Fun"]


def test_live_tv_is_off_for_kids_unless_allowed(env):
    c, db, _ = env
    kid = make_kid(c); as_profile(c, kid["id"])
    assert c.get("/api/live/channels").status_code == 403
    main = next(p for p in c.get("/api/profiles").json()["profiles"] if not p["kids"])
    as_profile(c, main["id"])
    c.put(f"/api/profiles/{kid['id']}", json={"settings": {"allow_live": True}})
    as_profile(c, kid["id"])
    assert c.get("/api/live/channels").status_code == 200
    assert c.get("/api/live/playlists").status_code == 403                            # but managing playlists never


def test_each_profile_has_its_own_progress_and_favorites(env):
    c, db, keys = env
    item = enc("Clean Fun"); key = keys["clean"]
    save = lambda pos: c.post(f"/api/progress/{key}", json={"source_id": "lib", "item_id": item, "title": "Clean Fun", "position": pos, "duration": 3600})  # noqa: E731
    main = next(p for p in c.get("/api/profiles").json()["profiles"] if not p["kids"])
    other = c.post("/api/profiles", json={"name": "Alex"}).json()
    save(1200)
    as_profile(c, other["id"])
    assert [r["title"] for r in c.get("/api/progress/recent").json()] == []           # Alex has watched nothing
    save(300)
    assert round(c.get("/api/progress/recent").json()[0]["position"]) == 300
    as_profile(c, main["id"])
    assert round(c.get("/api/progress/recent").json()[0]["position"]) == 1200          # Main's place is untouched

    # favorites and "recently watched" channels
    db.save_playlist("pl", "TV", "http://x/tv.m3u")
    db.replace_channels("pl", [("ch1", "One", ";News;", "", "http://x/1", enc("http://x/1")), ("ch2", "Two", ";News;", "", "http://x/2", enc("http://x/2"))])
    c.post("/api/live/channels/ch1/favorite", json={"favorite": True}); c.post("/api/live/channels/ch1/report", json={"ok": True})
    assert [x["name"] for x in c.get("/api/live/channels?favorites=true").json()["channels"]] == ["One"]
    as_profile(c, other["id"])
    assert c.get("/api/live/channels?favorites=true").json()["total"] == 0
    assert c.get("/api/live/channels?recent=true").json()["total"] == 0
    c.post("/api/live/channels/ch2/favorite", json={"favorite": True})
    assert [x["name"] for x in c.get("/api/live/channels?favorites=true").json()["channels"]] == ["Two"]


def test_profile_management_rules(env):
    c, db, _ = env
    main = next(p for p in c.get("/api/profiles").json()["profiles"] if not p["kids"])
    assert c.delete(f"/api/profiles/{main['id']}").status_code == 400                  # the last grown-up stays
    assert c.put(f"/api/profiles/{main['id']}", json={"kids": True}).status_code == 400
    kid = make_kid(c)
    assert c.put(f"/api/profiles/{kid['id']}", json={"name": "Sammy", "color": "#E2735F"}).json()["name"] == "Sammy"
    assert c.put(f"/api/profiles/{kid['id']}", json={"settings": {"max_hits": "lots"}}).status_code == 400
    c.post(f"/api/progress/{media_key('lib', 'x')}", json={"source_id": "lib", "item_id": "x", "position": 90, "duration": 100})
    assert c.delete(f"/api/profiles/{kid['id']}").status_code == 200
    assert [p["name"] for p in c.get("/api/profiles").json()["profiles"]] == ["Main"]
    for i in range(11):
        assert c.post("/api/profiles", json={"name": f"P{i}"}).status_code == 200
    assert c.post("/api/profiles", json={"name": "Too many"}).status_code == 400       # twelve is the limit


def test_leaving_a_kids_profile_can_ask_for_the_hush_password(tmp_path):
    cfg = Config(password="secret", secret_key="k" * 32, data_dir=tmp_path / "d"); cfg.data_dir.mkdir()
    c = TestClient(create_app(cfg))
    assert c.post("/api/login", json={"password": "secret"}).status_code == 200
    kid = make_kid(c)
    main = next(p for p in c.get("/api/profiles").json()["profiles"] if not p["kids"])
    assert c.put("/api/profiles/lock", json={"lock": True}).json() == {"lock": True}
    as_profile(c, kid["id"])
    assert c.post("/api/profiles/select", json={"id": main["id"]}).status_code == 403                       # a child cannot just switch back
    assert c.post("/api/profiles/select", json={"id": main["id"], "password": "nope"}).status_code == 403
    assert c.post("/api/profiles/select", json={"id": main["id"], "password": "secret"}).status_code == 200
    assert c.get("/api/profiles").json()["current"]["id"] == main["id"]


def test_existing_data_moves_into_the_first_profile(tmp_path):
    """A database from before profiles keeps its progress and favorite channels, under the first profile."""
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript("""
        CREATE TABLE progress (media_key TEXT PRIMARY KEY, source_id TEXT NOT NULL, item_id TEXT NOT NULL, title TEXT,
            position REAL NOT NULL DEFAULT 0, duration REAL, finished INTEGER DEFAULT 0, updated_at REAL NOT NULL);
        INSERT INTO progress VALUES ('k1','lib','i1','Old Movie',555,3600,0,1.0);
        CREATE TABLE channels (chan_key TEXT PRIMARY KEY, playlist TEXT NOT NULL, name TEXT NOT NULL, grp TEXT, logo TEXT,
            url TEXT NOT NULL, item_id TEXT NOT NULL, position INTEGER DEFAULT 0, favorite INTEGER DEFAULT 0,
            failures INTEGER DEFAULT 0, last_ok REAL);
        INSERT INTO channels VALUES ('c1','pl','Fav One',';A;','','http://x/1','i',0,1,0,5.0);
        INSERT INTO channels VALUES ('c2','pl','Plain','','', 'http://x/2','i',1,0,0,NULL);
        CREATE TABLE filters (media_key TEXT PRIMARY KEY, source_id TEXT NOT NULL, item_id TEXT NOT NULL, title TEXT, duration REAL,
            engine TEXT, data TEXT NOT NULL, updated_at REAL NOT NULL);
        INSERT INTO filters VALUES ('k1','lib','i1','Old Movie',100,'whisper','[{"category":"mild"},{"category":"strong"},{"category":"mild"}]',1.0);
    """)
    old.commit(); old.close()
    from hush.db import DB
    db = DB(path)
    first = db.list_profiles()[0]
    assert first["name"] == "Main" and not first["kids"]
    assert db.get_progress(first["id"], "k1")["position"] == 555
    assert [c["name"] for c in db.list_channels(favorites=True, profile_id=first["id"])] == ["Fav One"]
    assert [c["name"] for c in db.list_channels(recent=True, profile_id=first["id"])] == ["Fav One"]
    assert db._one("SELECT flags FROM filters WHERE media_key='k1'")["flags"] == json.dumps({"mild": 2, "strong": 1})
    assert DB(path).list_profiles()[0]["id"] == first["id"]                            # opening it again changes nothing


def test_profile_pictures(env):
    c, db, _ = env
    info = c.get("/api/profiles").json()
    assert "cat" in info["avatars"] and len(info["avatars"]) == 16 and info["profiles"][0]["avatar"] == ""     # existing profiles keep the initial
    kid = c.post("/api/profiles", json={"name": "Mia", "kids": True, "avatar": "panda", "color": "#E2735F"}).json()
    assert kid["avatar"] == "panda"
    assert c.post("/api/profiles", json={"name": "Hax", "avatar": "<script>"}).status_code == 400            # only known pictures
    assert c.put(f"/api/profiles/{kid['id']}", json={"avatar": "fox"}).json()["avatar"] == "fox"
    assert c.put(f"/api/profiles/{kid['id']}", json={"name": "Mia R"}).json()["avatar"] == "fox"              # an edit that skips it keeps it
    assert c.put(f"/api/profiles/{kid['id']}", json={"avatar": ""}).json()["avatar"] == ""                    # back to the initial letter
    assert next(p for p in c.get("/api/profiles").json()["profiles"] if p["id"] == kid["id"])["avatar"] == ""


def test_picture_column_is_added_to_older_databases(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript("CREATE TABLE profiles (id TEXT PRIMARY KEY, name TEXT NOT NULL, kids INTEGER DEFAULT 0, color TEXT, settings TEXT, position INTEGER DEFAULT 0, created_at REAL);"
                      "INSERT INTO profiles VALUES ('p1','Main',0,'#A99CF0','{}',0,1.0);")
    old.commit(); old.close()
    from hush.db import DB
    db = DB(path)
    assert db.get_profile("p1")["avatar"] is None or db.get_profile("p1")["avatar"] == ""
    db.save_profile("p1", "Main", False, "#A99CF0", {}, "owl")
    assert db.get_profile("p1")["avatar"] == "owl"


def test_library_version_changes_with_the_library(tmp_path):
    from hush.db import DB
    db = DB(tmp_path / "v.db")
    before = db.library_version()
    db.record_library("src", [("k1", "src", "a.mkv", "A")], 1.0)
    assert db.library_version() != before



def test_my_list_follows_library_shows_and_remembers_status(env, monkeypatch):
    c, db, keys = env
    # nothing watched yet: the list is empty
    assert c.get("/api/watchlist").json() == []
    # watching an episode puts the show under Watching by itself, with the next episode to play
    ep1 = media_key("lib", enc("ep1"))
    db.save_progress("p1", ep1, "lib", enc("ep1"), "Ep 1", 95.0, 100.0)            # finished
    items = c.get("/api/watchlist").json()
    assert [(i["ref"], i["status"], i["auto"]) for i in items] == [("show:sh1", "watching", True)]
    assert items[0]["progress"]["unwatched"] == 1 and items[0]["progress"]["next"]["episode"] == 2
    # choosing a status keeps it
    assert c.post("/api/watchlist", json={"show_key": "sh1", "status": "dropped"}).status_code == 200
    assert [(i["status"], i["auto"]) for i in c.get("/api/watchlist").json()] == [("dropped", False)]
    assert c.get("/api/library/shows/sh1").json()["list_status"] == "dropped"
    # a show that is not in the library is followed by its TVmaze id
    from hush import mylist
    monkeypatch.setattr(mylist, "show_info", lambda tid: {"title": "Elsewhere", "year": 2026, "network": "HBO", "status": "Running", "poster_url": None, "imdb": None})
    monkeypatch.setattr(mylist, "next_airing", lambda tid: {"next": {"season": 1, "episode": 3, "title": "Three", "airs_at": 2e9}, "status": "Running"})
    assert c.post("/api/watchlist", json={"tvmaze_id": "123", "status": "planned"}).status_code == 200
    ext = [i for i in c.get("/api/watchlist").json() if i["ref"] == "tm:123"][0]
    assert ext["title"] == "Elsewhere" and not ext["in_library"] and ext["airing"]["episode"] == 3
    assert c.delete("/api/watchlist?ref=tm:123").status_code == 200
    assert all(i["ref"] != "tm:123" for i in c.get("/api/watchlist").json())


def test_kids_cannot_follow_outside_shows(env):
    c, db, keys = env
    kid = make_kid(c)
    as_profile(c, kid["id"])
    assert c.post("/api/watchlist", json={"tvmaze_id": "123", "status": "planned"}).status_code == 403
    assert c.get("/api/watchlist/search?q=anything").json() == []


def test_channels_keep_their_numbers_for_good(tmp_path):
    from hush.db import DB
    db = DB(tmp_path / "n.db")
    rows = lambda *names: [(f"k{n}", n, ";", "", f"http://x/{n}", enc(f"http://x/{n}"), "") for n in names]  # noqa: E731
    db.replace_channels("pl", rows("Charlie", "Alpha", "Bravo"))
    nums = {c["chan_key"]: c["number"] for c in db.list_channels(profile_id="p")}
    assert nums == {"kAlpha": 1, "kBravo": 2, "kCharlie": 3}                         # first numbering: alphabetical
    db.replace_channels("pl", rows("Charlie", "Alpha", "Bravo", "Aardvark"))        # a re-read adds a channel; nothing moves
    nums = {c["chan_key"]: c["number"] for c in db.list_channels(profile_id="p")}
    assert nums["kAlpha"] == 1 and nums["kBravo"] == 2 and nums["kCharlie"] == 3 and nums["kAardvark"] == 4
    db.replace_channels("pl", rows("Alpha", "Bravo"))                               # Charlie and Aardvark leave...
    db.replace_channels("pl", rows("Alpha", "Bravo", "Charlie"))                    # ...and Charlie comes back: same number
    assert {c["chan_key"]: c["number"] for c in db.list_channels(profile_id="p")}["kCharlie"] == 3
    with pytest.raises(ValueError, match="Channel 1 is Alpha"):
        db.set_channel_number("kBravo", 1)
    assert db.set_channel_number("kBravo", 1, swap=True)["swapped"] == "Alpha"
    nums = {c["chan_key"]: c["number"] for c in db.list_channels(profile_id="p")}
    assert nums["kBravo"] == 1 and nums["kAlpha"] == 2
    assert db.set_channel_number("kAlpha", 500)["number"] == 500
    assert [r["number"] for r in db.lineup()] == [1, 3, 500]
    assert db.renumber("name") == 3 and [r["number"] for r in db.lineup()] == [1, 2, 3]
    with pytest.raises(ValueError):
        db.set_channel_number("kAlpha", 0)


def test_numbers_are_given_to_channels_that_existed_before(tmp_path):
    import sqlite3
    from hush.db import DB
    path = tmp_path / "old.db"
    db = DB(path)
    db.replace_channels("pl", [("kb", "Beta", ";", "", "http://x/b", enc("http://x/b"), ""), ("ka", "Alpha", ";", "", "http://x/a", enc("http://x/a"), "")])
    c = sqlite3.connect(path)
    c.execute("DROP TABLE channel_numbers")                                          # a database from before numbering existed
    c.commit(); c.close()
    db2 = DB(path)
    assert {r["key"]: r["number"] for r in db2.lineup()} == {"ka": 1, "kb": 2}


def test_ranges_leave_room_for_each_category_to_grow(tmp_path):
    from hush.db import DB, plan_ranges, primary_group
    assert primary_group(";News;Sports;") == "News" and primary_group("") == ""
    plan = plan_ranges({"Sports": 150, "News": 40, "Movies": 9, "Zoo": 3, "Kids": 2})
    names = [p[0] for p in plan]
    assert names == ["News", "Sports", "Movies", "Other"]                         # known categories first, tiny ones share "Other" at the end
    blocks = {c: (a, b) for c, a, b in plan}
    assert blocks["News"] == (100, 199) and blocks["Sports"] == (200, 499) and blocks["Movies"] == (500, 599) and blocks["Other"] == (600, 699)
    assert all(a % 100 == 0 for _, a, _ in plan)

    db = DB(tmp_path / "r.db")
    rows = [(f"n{i}", f"News {i:02d}", ";News;", "", f"http://x/n{i}", enc(f"http://x/n{i}"), "") for i in range(12)]
    rows += [(f"s{i}", f"Sport {i:02d}", ";Sports;", "", f"http://x/s{i}", enc(f"http://x/s{i}"), "") for i in range(9)]
    db.replace_channels("pl", rows)
    assert db.renumber("ranges") == 21
    nums = {c["chan_key"]: c["number"] for c in db.list_channels(limit=100, profile_id="p")}
    assert nums["n0"] == 100 and nums["n11"] == 111 and nums["s0"] == 200 and nums["s8"] == 208     # a block starts on a hundred, alphabetical inside
    # a channel that arrives later goes into its own category's block, after the others, and keeps that number
    db.replace_channels("pl", rows + [("n99", "News 99", ";News;", "", "http://x/n99", enc("http://x/n99"), ""),
                                      ("z1", "Brand new", ";Cooking;", "", "http://x/z1", enc("http://x/z1"), "")])
    nums = {c["chan_key"]: c["number"] for c in db.list_channels(limit=100, profile_id="p")}
    assert nums["n99"] == 112 and nums["s0"] == 200 and nums["n0"] == 100
    assert 300 <= nums["z1"] < 400 or nums["z1"] >= 300                           # an unknown category lands in "Other" (its own block)
    # a full block opens another one at the end instead of running into the next category
    for i in range(100):
        db.replace_channels("pl", rows + [(f"x{j}", f"Extra {j}", ";News;", "", f"http://x/e{j}", enc(f"http://x/e{j}"), "") for j in range(i + 1)])
        if len(db.number_ranges()) > 3 + 0 and any(r["category"] == "News" and r["start"] > 199 for r in db.number_ranges()):
            break
    assert any(r["category"] == "News" and r["start"] >= 400 for r in db.number_ranges())
    assert len({c["number"] for c in db.list_channels(limit=500, profile_id="p")}) == len(db.list_channels(limit=500, profile_id="p"))
