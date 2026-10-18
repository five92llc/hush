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
CREATE TABLE IF NOT EXISTS library_items (
    media_key   TEXT PRIMARY KEY,
    source_id   TEXT NOT NULL,       -- source the item plays from
    origin      TEXT NOT NULL,       -- source whose folders it was found in
    item_id     TEXT NOT NULL,
    title       TEXT,
    first_seen  REAL NOT NULL,
    last_seen   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS library_origin ON library_items(origin);
CREATE TABLE IF NOT EXISTS meta (
    media_key   TEXT PRIMARY KEY,
    source_id   TEXT NOT NULL,
    item_id     TEXT NOT NULL,
    kind        TEXT NOT NULL,       -- movie | episode
    title       TEXT,                -- movie title, or episode title
    year        INTEGER,
    show_key    TEXT,
    season      INTEGER,
    episode     INTEGER,
    overview    TEXT,
    genres      TEXT,                -- JSON list
    rating      REAL,
    runtime     INTEGER,             -- minutes
    art         INTEGER DEFAULT 0,   -- 1 when data/art/<media_key>.jpg exists
    ids         TEXT,                -- JSON {imdb, tmdb, ...}
    provider    TEXT,                -- nfo | tmdb | wikipedia | tvmaze | name | manual
    locked      INTEGER DEFAULT 0,   -- set when you fixed it by hand: never overwritten
    updated_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS meta_show ON meta(show_key);
CREATE TABLE IF NOT EXISTS shows (
    show_key    TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    year        INTEGER,
    overview    TEXT,
    genres      TEXT,
    rating      REAL,
    art         INTEGER DEFAULT 0,
    ids         TEXT,
    provider    TEXT,
    locked      INTEGER DEFAULT 0,
    updated_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS renames (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    batch       TEXT NOT NULL,
    source_id   TEXT NOT NULL,
    kind        TEXT NOT NULL,       -- mkdir | move | rmdir | rekey
    src         TEXT NOT NULL,       -- absolute paths (rekey: "media_key|item_id")
    dst         TEXT NOT NULL,
    created_at  REAL NOT NULL,
    undone      INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS renames_batch ON renames(batch);
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

    def last_job_blocked(self, media_key: str) -> bool:
        """True if the newest scan of this title failed or was cancelled (so auto-scan
        does not retry it forever). A restart is not the title's fault."""
        row = self._one("SELECT status, error FROM jobs WHERE media_key=? "
                        "ORDER BY created_at DESC LIMIT 1", (media_key,))
        return bool(row and (row["status"] == "cancelled" or
                             (row["status"] == "error" and row["error"] != "Server restarted")))

    def resume_interrupted_jobs(self) -> list[str]:
        """Jobs that were queued or running when the server stopped go back in the queue."""
        ids = [r["id"] for r in self._all(
            "SELECT id FROM jobs WHERE status IN ('queued','running') ORDER BY created_at")]
        self._exec("UPDATE jobs SET status='queued', stage='queued', progress=0, error=NULL, "
                   "updated_at=? WHERE status IN ('queued','running')", (time.time(),))
        return ids

    def active_jobs(self) -> list[dict[str, Any]]:
        return self._all("SELECT * FROM jobs WHERE status IN ('queued','running') ORDER BY created_at")

    def blocked_titles(self) -> list[dict[str, Any]]:
        """Newest job of every title whose latest scan failed or was cancelled."""
        seen, out = set(), []
        for j in self._all("SELECT * FROM jobs ORDER BY created_at DESC LIMIT 2000"):
            if j["media_key"] in seen:
                continue
            seen.add(j["media_key"])
            if j["status"] in ("error", "cancelled"):
                out.append(j)
        return out

    # ---- library index ---------------------------------------------------
    def record_library(self, origin: str, items: list[tuple[str, str, str, str]], now: float) -> int:
        """Remember titles seen in a refresh. items = (media_key, source_id, item_id, title).
        Returns how many were not known before."""
        with self._lock:
            known = {r[0] for r in self._conn.execute(
                "SELECT media_key FROM library_items WHERE origin=?", (origin,))}
            self._conn.executemany(
                "INSERT INTO library_items(media_key,source_id,origin,item_id,title,first_seen,last_seen) "
                "VALUES(?,?,?,?,?,?,?) ON CONFLICT(media_key) DO UPDATE SET last_seen=excluded.last_seen, "
                "title=excluded.title, origin=excluded.origin",
                [(k, s, origin, i, t, now, now) for k, s, i, t in items])
            self._conn.commit()
        return sum(1 for k, *_ in items if k not in known)

    def prune_library(self, origin: str, before: float) -> int:
        """Forget titles of this source that a complete refresh did not find any more."""
        with self._lock:
            c = self._conn
            gone = [r[0] for r in c.execute("SELECT media_key FROM library_items WHERE origin=? AND last_seen<?",
                                            (origin, before))]
            c.executemany("DELETE FROM meta WHERE media_key=?", [(k,) for k in gone])
            c.execute("DELETE FROM library_items WHERE origin=? AND last_seen<?", (origin, before))
            c.execute("DELETE FROM shows WHERE show_key NOT IN (SELECT DISTINCT show_key FROM meta "
                      "WHERE show_key IS NOT NULL)")
            c.commit()
        return len(gone)

    def library_stats(self) -> dict[str, int]:
        total = self._one("SELECT COUNT(*) n FROM library_items")["n"]
        scanned = self._one("SELECT COUNT(*) n FROM library_items l JOIN filters f "
                            "ON f.media_key=l.media_key")["n"]
        return {"titles": total, "scanned": scanned}

    def delete_old_jobs(self, before: float) -> int:
        return self._exec("DELETE FROM jobs WHERE status IN ('done','error','cancelled') "
                          "AND updated_at<?", (before,)).rowcount

    # ---- titles, shows and artwork ------------------------------------------
    _META_JSON = ("genres", "ids")

    def _decode(self, row: dict | None) -> dict | None:
        if row:
            for k in self._META_JSON:
                if k in row:
                    row[k] = json.loads(row[k]) if row[k] else ([] if k == "genres" else {})
        return row

    def get_meta(self, media_key: str) -> dict | None:
        return self._decode(self._one("SELECT * FROM meta WHERE media_key=?", (media_key,)))

    def save_meta(self, m: dict) -> None:
        cols = ["media_key", "source_id", "item_id", "kind", "title", "year", "show_key", "season",
                "episode", "overview", "genres", "rating", "runtime", "art", "ids", "provider", "locked"]
        row = {c: m.get(c) for c in cols}
        row["genres"] = json.dumps(m.get("genres") or [])
        row["ids"] = json.dumps(m.get("ids") or {})
        row["art"] = int(bool(m.get("art")))
        row["locked"] = int(bool(m.get("locked")))
        self._exec(f"INSERT OR REPLACE INTO meta({','.join(cols)},updated_at) VALUES({','.join('?' * len(cols))},?)",
                   (*row.values(), time.time()))

    def get_show(self, show_key: str) -> dict | None:
        return self._decode(self._one("SELECT * FROM shows WHERE show_key=?", (show_key,)))

    def save_show(self, s: dict) -> None:
        cols = ["show_key", "title", "year", "overview", "genres", "rating", "art", "ids", "provider", "locked"]
        row = {c: s.get(c) for c in cols}
        row["genres"] = json.dumps(s.get("genres") or [])
        row["ids"] = json.dumps(s.get("ids") or {})
        row["art"] = int(bool(s.get("art")))
        row["locked"] = int(bool(s.get("locked")))
        self._exec(f"INSERT OR REPLACE INTO shows({','.join(cols)},updated_at) VALUES({','.join('?' * len(cols))},?)",
                   (*row.values(), time.time()))

    def library_without_meta(self, limit: int = 100000) -> list[dict]:
        return self._all("SELECT l.* FROM library_items l LEFT JOIN meta m ON m.media_key=l.media_key "
                         "WHERE m.media_key IS NULL ORDER BY l.title LIMIT ?", (limit,))

    def list_movies(self) -> list[dict]:
        rows = self._all("SELECT m.*, (f.media_key IS NOT NULL) AS scanned FROM meta m "
                         "LEFT JOIN filters f ON f.media_key=m.media_key WHERE m.kind='movie' "
                         "ORDER BY lower(m.title), m.year")
        return [self._decode(r) for r in rows]

    def list_shows(self) -> list[dict]:
        rows = self._all(
            "SELECT s.*, COUNT(m.media_key) AS episodes, COUNT(DISTINCT m.season) AS seasons, "
            "SUM(f.media_key IS NOT NULL) AS scanned FROM shows s "
            "LEFT JOIN meta m ON m.show_key=s.show_key LEFT JOIN filters f ON f.media_key=m.media_key "
            "GROUP BY s.show_key ORDER BY lower(s.title)")
        return [self._decode(r) for r in rows]

    def episodes_of(self, show_key: str) -> list[dict]:
        rows = self._all("SELECT m.*, (f.media_key IS NOT NULL) AS scanned FROM meta m "
                         "LEFT JOIN filters f ON f.media_key=m.media_key WHERE m.show_key=? "
                         "ORDER BY m.season, m.episode", (show_key,))
        return [self._decode(r) for r in rows]

    def rekey(self, old: str, new: str, source_id: str, item_id: str) -> None:
        """A file moved: carry its filter, scans, details and library entry over to the new key."""
        with self._lock:
            c = self._conn
            c.execute("DELETE FROM filters WHERE media_key=?", (new,))
            c.execute("UPDATE filters SET media_key=?, source_id=?, item_id=? WHERE media_key=?",
                      (new, source_id, item_id, old))
            c.execute("UPDATE jobs SET media_key=?, source_id=?, item_id=? WHERE media_key=?",
                      (new, source_id, item_id, old))
            c.execute("DELETE FROM meta WHERE media_key=?", (new,))
            c.execute("UPDATE meta SET media_key=?, source_id=?, item_id=? WHERE media_key=?",
                      (new, source_id, item_id, old))
            c.execute("DELETE FROM library_items WHERE media_key=?", (new,))
            c.execute("UPDATE library_items SET media_key=?, source_id=?, item_id=? WHERE media_key=?",
                      (new, source_id, item_id, old))
            c.commit()

    # ---- rename journal --------------------------------------------------------------
    def journal(self, batch: str, source_id: str, kind: str, src: str, dst: str) -> int:
        return self._exec("INSERT INTO renames(batch,source_id,kind,src,dst,created_at) VALUES(?,?,?,?,?,?)",
                          (batch, source_id, kind, src, dst, time.time())).lastrowid

    def drop_journal(self, ids: list[int]) -> None:
        for i in ids:
            self._exec("DELETE FROM renames WHERE id=?", (i,))

    def rename_batches(self, limit: int = 20) -> list[dict]:
        return self._all("SELECT batch, source_id, MIN(created_at) AS at, COUNT(*) AS steps, "
                         "SUM(kind='move') AS moves, MIN(undone) AS undone FROM renames "
                         "GROUP BY batch ORDER BY at DESC LIMIT ?", (limit,))

    def rename_steps(self, batch: str) -> list[dict]:
        return self._all("SELECT * FROM renames WHERE batch=? ORDER BY id", (batch,))

    def mark_undone(self, batch: str) -> None:
        self._exec("UPDATE renames SET undone=1 WHERE batch=?", (batch,))

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
