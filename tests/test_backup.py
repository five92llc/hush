"""Backups of the database and transcripts, and putting them back."""
from hush import backup
from hush.config import Config
from hush.db import DB


def test_a_backup_can_be_restored(tmp_path):
    cfg = Config(data_dir=tmp_path / "d"); cfg.data_dir.mkdir(); cfg.cache_dir.mkdir()
    db = DB(cfg.db_path)
    db.set_setting("note", "keep me")
    (cfg.cache_dir / "abc123.words.json").write_text("{}")
    out = backup.create(cfg)
    assert backup.listing(cfg)[0]["name"] == out.name and oct(out.stat().st_mode)[-3:] == "600"
    db.set_setting("note", "changed")
    (cfg.cache_dir / "abc123.words.json").unlink()
    db._conn.close()
    backup.restore(cfg, out)
    assert DB(cfg.db_path).get_setting("note") == "keep me" and (cfg.cache_dir / "abc123.words.json").exists()
    assert cfg.db_path.with_name("hush.db.before-restore").exists()


def test_only_the_newest_backups_are_kept(tmp_path, monkeypatch):
    cfg = Config(data_dir=tmp_path / "d"); cfg.data_dir.mkdir(); cfg.cache_dir.mkdir(); DB(cfg.db_path)
    monkeypatch.setattr(backup, "KEEP", 2)
    stamps = iter(["20260101-000001", "20260101-000002", "20260101-000003"])
    monkeypatch.setattr(backup.time, "strftime", lambda *_: next(stamps))
    for _ in range(3):
        backup.create(cfg)
    assert [b["name"][12:27] for b in backup.listing(cfg)] == ["20260101-000003", "20260101-000002"]
