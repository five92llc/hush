"""Your own words, words never to mute, and scenes marked to be skipped."""
from fastapi.testclient import TestClient

from hush.analysis.matcher import Word, WordList
from hush.app import create_app
from hush.config import Config
from hush.sources import media_key


def test_own_words_are_added_and_allowed_words_left_alone():
    wl = WordList()
    words = [Word("what", 0, 0.2), Word("blorp", 0.3, 0.5), Word("damn", 1, 1.2)]
    assert [d["words"][0] for d in wl.find(words)] == ["damn"]
    wl.load({"add": {"mild": ["blorp"]}, "allow": ["damn"]})
    assert [d["words"][0] for d in wl.find(words)] == ["blorp"]


def test_word_settings_and_scene_skip(tmp_path):
    cfg = Config(password="", secret_key="k" * 32, data_dir=tmp_path / "d"); cfg.data_dir.mkdir(); cfg.cache_dir.mkdir()
    c = TestClient(create_app(cfg))
    cat = c.get("/api/wordlist").json()["categories"][0]["id"]
    saved = c.put("/api/wordlist", json={"add": {cat: ["Blorp!", "*", ""], "nope": ["x"]}, "allow": ["damn"]}).json()
    assert saved["add"] == {cat: ["blorp"]} and saved["allow"] == ["damn"]      # a bare * would mute everything
    key = media_key("s", "i")
    body = {"source_id": "s", "item_id": "i", "ranges": [{"start": 5, "end": 60, "source": "manual", "action": "skip"}]}
    assert c.put(f"/api/filters/{key}", json=body).json()["ranges"][0]["action"] == "skip"
    assert c.get("/api/config").json()["scene_skip"] is False
    assert "60.000" not in c.get(f"/api/filters/{key}/export?format=edl").text           # off: the scene plays
    c.put("/api/wordlist/scene-skip", json={"on": True})
    assert "5.000\t60.000\t0" in c.get(f"/api/filters/{key}/export?format=edl").text
