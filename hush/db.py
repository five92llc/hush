"""SQLite storage for filters, analysis jobs and runtime-added sources."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS filters (
    media_key   TEXT PRIMARY KEY,
    source_id   TEXT NOT NULL,
    item_id     TEXT NOT NULL,
    title       TEXT,
    duration    REAL,
    engine      TEXT,
    data        TEXT NOT NULL,       -- JSON list of ranges
    updated_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    media_key   TEXT NOT NULL,
    source_id   TEXT NOT NULL,
    item_id     TEXT NOT NULL,
    title       TEXT,
    status      TEXT NOT NULL,       -- queued | running | done | error | cancelled
    stage       TEXT,
    progress    REAL DEFAULT 0,
    error       TEXT,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_media ON jobs(media_key);
CREATE TABLE IF NOT EXISTS sources (
    id          TEXT PRIMARY KEY,
    data        TEXT NOT NULL        -- JSON source definition
);
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL
);
"""


class DB:
    def __init__(self, path: Path):
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def _exec(self, sql: str, args: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, args)
            self._conn.commit()
            return cur

    def _all(self, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, args).fetchall()]

    def _one(self, sql: str, args: tuple = ()) -> dict[str, Any] | None:
        rows = self._all(sql, args)
        return rows[0] if rows else None

    # ---- filters ---------------------------------------------------------
    def get_filter(self, media_key: str) -> dict[str, Any] | None:
        row = self._one("SELECT * FROM filters WHERE media_key=?", (media_key,))
        if row:
            row["ranges"] = json.loads(row.pop("data"))
        return row

    def save_filter(self, media_key: str, source_id: str, item_id: str, title: str,
                    duration: float | None, engine: str, ranges: list[dict]) -> None:
        self._exec(
            """INSERT INTO filters(media_key,source_id,item_id,title,duration,engine,data,updated_at)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(media_key) DO UPDATE SET title=excluded.title,
                 duration=excluded.duration, engine=excluded.engine,
                 data=excluded.data, updated_at=excluded.updated_at""",
            (media_key, source_id, item_id, title, duration, engine,
             json.dumps(ranges), time.time()),
        )

    def delete_filter(self, media_key: str) -> None:
        self._exec("DELETE FROM filters WHERE media_key=?", (media_key,))

    def filtered_keys(self, keys: list[str]) -> set[str]:
        if not keys:
            return set()
        q = ",".join("?" * len(keys))
        return {r["media_key"] for r in self._all(
            f"SELECT media_key FROM filters WHERE media_key IN ({q})", tuple(keys))}

    # ---- jobs ------------------------------------------------------------
    def create_job(self, job: dict[str, Any]) -> None:
        now = time.time()
        self._exec(
            """INSERT INTO jobs(id,media_key,source_id,item_id,title,status,stage,progress,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (job["id"], job["media_key"], job["source_id"], job["item_id"], job.get("title"),
             "queued", "queued", 0.0, now, now),
        )

    def update_job(self, job_id: str, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = time.time()
        cols = ",".join(f"{k}=?" for k in fields)
        self._exec(f"UPDATE jobs SET {cols} WHERE id=?", (*fields.values(), job_id))

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM jobs WHERE id=?", (job_id,))

    def list_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._all("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,))

    def active_job_for(self, media_key: str) -> dict[str, Any] | None:
        return self._one(
            "SELECT * FROM jobs WHERE media_key=? AND status IN ('queued','running') "
            "ORDER BY created_at DESC LIMIT 1", (media_key,))

    def fail_interrupted_jobs(self) -> None:
        self._exec("UPDATE jobs SET status='error', error='Server restarted' "
                   "WHERE status IN ('queued','running')")

    # ---- runtime sources -------------------------------------------------
    def list_sources(self) -> list[dict[str, Any]]:
        return [json.loads(r["data"]) for r in self._all("SELECT data FROM sources")]

    def save_source(self, src: dict[str, Any]) -> None:
        self._exec("INSERT OR REPLACE INTO sources(id,data) VALUES(?,?)",
                   (src["id"], json.dumps(src)))

    def delete_source(self, source_id: str) -> None:
        self._exec("DELETE FROM sources WHERE id=?", (source_id,))

    # ---- settings --------------------------------------------------------
    def get_setting(self, key: str, default: Any = None) -> Any:
        row = self._one("SELECT value FROM settings WHERE key=?", (key,))
        return json.loads(row["value"]) if row else default

    def set_setting(self, key: str, value: Any) -> None:
        self._exec("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",
                   (key, json.dumps(value)))
