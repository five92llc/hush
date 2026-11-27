"""Nightly backups: the database (history, marks, scan results, channel numbers, settings) and the scan transcripts, in one .tar.gz.

Restore on the server, with Hush stopped:
    sudo systemctl stop hush && .venv/bin/python -m hush.backup restore <file> && sudo systemctl start hush
"""
from __future__ import annotations

import re
import shutil
import sqlite3
import sys
import tarfile
import tempfile
import time
from pathlib import Path

NAME = re.compile(r"^hush-backup-\d{8}-\d{6}\.tar\.gz$")
KEEP = 14


def folder(cfg) -> Path:
    return Path(cfg.backup_dir).expanduser() if cfg.backup_dir else cfg.data_dir / "backups"


def listing(cfg) -> list[dict]:
    d = folder(cfg)
    files = sorted((f for f in d.glob("hush-backup-*.tar.gz") if NAME.match(f.name)), reverse=True) if d.is_dir() else []
    return [{"name": f.name, "size": f.stat().st_size, "at": f.stat().st_mtime} for f in files]


def create(cfg) -> Path:
    """Write a new backup (safe while Hush is running) and drop the oldest beyond KEEP."""
    d = folder(cfg)
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"hush-backup-{time.strftime('%Y%m%d-%H%M%S')}.tar.gz"
    part = out.with_suffix(".part")
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "hush.db"
        src, dst = sqlite3.connect(cfg.db_path), sqlite3.connect(copy)
        try:
            src.backup(dst)                        # a consistent copy, even mid-write
        finally:
            src.close(); dst.close()
        with tarfile.open(part, "w:gz") as tar:
            tar.add(copy, "hush.db")
            for f in cfg.cache_dir.glob("*.words.json"):
                tar.add(f, f"cache/{f.name}")
    part.chmod(0o600)                              # it holds the same private settings as the database
    part.rename(out)
    for old in listing(cfg)[KEEP:]:
        (d / old["name"]).unlink(missing_ok=True)
    return out


def restore(cfg, archive: Path) -> None:
    """Put a backup back. The database being replaced is kept beside it as hush.db.before-restore. Hush must be stopped."""
    with tempfile.TemporaryDirectory() as tmp, tarfile.open(archive, "r:gz") as tar:
        members = [m for m in tar.getmembers() if m.isfile() and (m.name == "hush.db" or re.fullmatch(r"cache/[0-9A-Za-z]+\.words\.json", m.name))]
        if not any(m.name == "hush.db" for m in members):
            raise ValueError("This is not a Hush backup: there is no database in it")
        for m in members:
            target = Path(tmp) / m.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(tar.extractfile(m).read())
        check = sqlite3.connect(Path(tmp) / "hush.db")
        try:
            if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("The database in this backup is damaged")
        finally:
            check.close()
        if cfg.db_path.exists():
            shutil.copy2(cfg.db_path, cfg.db_path.with_name("hush.db.before-restore"))
        for extra in ("-wal", "-shm"):
            Path(str(cfg.db_path) + extra).unlink(missing_ok=True)
        shutil.copy2(Path(tmp) / "hush.db", cfg.db_path)
        cfg.cache_dir.mkdir(parents=True, exist_ok=True)
        for f in (Path(tmp) / "cache").glob("*.words.json"):
            shutil.copy2(f, cfg.cache_dir / f.name)


if __name__ == "__main__":
    from .config import load_config
    config = load_config()
    if len(sys.argv) == 3 and sys.argv[1] == "restore":
        arg = Path(sys.argv[2])
        restore(config, arg if arg.exists() else folder(config) / sys.argv[2])
        print("Restored. Start Hush again.")
    elif len(sys.argv) == 2 and sys.argv[1] == "now":
        print(create(config))
    else:
        print("Use: python -m hush.backup now | restore <file>")
