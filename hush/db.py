"""SQLite storage for filters, analysis jobs and runtime-added sources."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import unicodedata
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
    flags       TEXT,                -- JSON {category: moments}, for kids profiles
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
    cert        TEXT,                -- content rating such as PG-13 or TV-MA
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
    cert        TEXT,
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
CREATE TABLE IF NOT EXISTS profiles (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    kids        INTEGER DEFAULT 0,
    color       TEXT,
    avatar      TEXT,                -- picture id (see profiles.AVATARS); empty = the initial letter
    settings    TEXT,                -- JSON: what a kids profile may see
    position    INTEGER DEFAULT 0,
    created_at  REAL
);
CREATE TABLE IF NOT EXISTS progress (
    profile_id  TEXT NOT NULL DEFAULT '',
    media_key   TEXT NOT NULL,
    source_id   TEXT NOT NULL,
    item_id     TEXT NOT NULL,
    title       TEXT,
    position    REAL NOT NULL DEFAULT 0,   -- seconds; 0 once finished
    duration    REAL,
    finished    INTEGER DEFAULT 0,
    updated_at  REAL NOT NULL,
    PRIMARY KEY (profile_id, media_key)
);
CREATE TABLE IF NOT EXISTS channel_marks (
    profile_id  TEXT NOT NULL,
    chan_key    TEXT NOT NULL,
    favorite    INTEGER DEFAULT 0,
    last_ok     REAL,                -- when this profile last watched it
    PRIMARY KEY (profile_id, chan_key)
);
CREATE TABLE IF NOT EXISTS playlists (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    url         TEXT NOT NULL,
    channels    INTEGER DEFAULT 0,
    updated_at  REAL,
    error       TEXT
);
CREATE TABLE IF NOT EXISTS channels (
    chan_key    TEXT PRIMARY KEY,    -- hash of the stream address
    playlist    TEXT NOT NULL,
    name        TEXT NOT NULL,
    letter      TEXT,                -- first letter or digit, for the A-Z picker
    grp         TEXT,                -- ";News;Sport;" so one channel can be in several groups
    logo        TEXT,
    url         TEXT NOT NULL,
    item_id     TEXT NOT NULL,       -- how the player opens it
    position    INTEGER DEFAULT 0,
    favorite    INTEGER DEFAULT 0,
    failures    INTEGER DEFAULT 0,   -- playback failures in a row; two hide the channel
    last_ok     REAL
);
CREATE INDEX IF NOT EXISTS channels_playlist ON channels(playlist);
CREATE TABLE IF NOT EXISTS sources (
    id          TEXT PRIMARY KEY,
    data        TEXT NOT NULL        -- JSON source definition
);
CREATE TABLE IF NOT EXISTS probes (
    source_id   TEXT NOT NULL,
    item_id     TEXT NOT NULL,
    data        TEXT NOT NULL,       -- JSON of what ffprobe found, so a channel starts fast after a restart
    updated_at  REAL NOT NULL,
    PRIMARY KEY (source_id, item_id)
);
CREATE TABLE IF NOT EXISTS programmes (
    tvg_id      TEXT NOT NULL,
    start       REAL NOT NULL,
    stop        REAL NOT NULL,
    title       TEXT,
    descr       TEXT
);
CREATE INDEX IF NOT EXISTS programmes_chan ON programmes(tvg_id, start);
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL
);
"""


def _flag_counts(data) -> dict[str, int]:
    """How many flagged moments a saved filter has in each word category (all of them, even ones an adult allowed)."""
    try:
        ranges = json.loads(data) if isinstance(data, str) else (data or [])
    except ValueError:
        return {}
    counts: dict[str, int] = {}
    for r in ranges:
        cat = r.get("category") or "manual"
        counts[cat] = counts.get(cat, 0) + 1
    return counts


def letter_of(name: str, skip_articles: bool = False) -> str:
    """The bucket a title files under in the A-Z / 0-9 picker: its first letter or digit,
    ignoring leading symbols and accents. Anything else (other alphabets) files under "*"."""
    text = (name or "").strip()
    if skip_articles:
        low = text.lower()
        for art in ("the ", "a ", "an "):
            if low.startswith(art) and len(text) > len(art):
                text = text[len(art):]
                break
    for ch in text:
        if ch.isdigit() and ch.isascii():
            return ch
        base = unicodedata.normalize("NFKD", ch)[:1].upper()
        if "A" <= base <= "Z":
            return base
        if ch.isalnum():
            return "*"
    return "*"


class DB:
    def __init__(self, path: Path):
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        self._migrate()
        self._conn.commit()

    def _columns(self, table: str) -> set[str]:
        return {r[1] for r in self._conn.execute(f"PRAGMA table_info({table})")}

    def _migrate(self) -> None:
        """Bring databases made by an older version up to date."""
        c = self._conn
        if "letter" not in self._columns("channels"):
            c.execute("ALTER TABLE channels ADD COLUMN letter TEXT")
            c.executemany("UPDATE channels SET letter=? WHERE chan_key=?",
                          [(letter_of(n), k) for k, n in c.execute("SELECT chan_key, name FROM channels")])
        c.execute("CREATE INDEX IF NOT EXISTS channels_letter ON channels(letter)")

        # Profiles: everything that existed before belongs to the first profile.
        if not c.execute("SELECT 1 FROM profiles LIMIT 1").fetchone():
            c.execute("INSERT INTO profiles(id,name,kids,color,settings,position,created_at) VALUES('p1','Main',0,'#A99CF0','{}',0,?)",
                      (time.time(),))
        first = c.execute("SELECT id FROM profiles WHERE kids=0 ORDER BY position, created_at LIMIT 1").fetchone()[0]
        if "profile_id" not in self._columns("progress"):
            c.execute("ALTER TABLE progress RENAME TO progress_old")
            c.execute("DROP INDEX IF EXISTS progress_recent")
            c.executescript(SCHEMA[SCHEMA.index("CREATE TABLE IF NOT EXISTS progress ("):SCHEMA.index("CREATE TABLE IF NOT EXISTS channel_marks")])
            c.execute("INSERT INTO progress(profile_id,media_key,source_id,item_id,title,position,duration,finished,updated_at) "
                      "SELECT ?,media_key,source_id,item_id,title,position,duration,finished,updated_at FROM progress_old", (first,))
            c.execute("DROP TABLE progress_old")
        c.execute("CREATE INDEX IF NOT EXISTS progress_recent ON progress(profile_id, finished, updated_at)")
        if not c.execute("SELECT 1 FROM channel_marks LIMIT 1").fetchone():
            c.execute("INSERT OR IGNORE INTO channel_marks(profile_id,chan_key,favorite,last_ok) "
                      "SELECT ?,chan_key,favorite,last_ok FROM channels WHERE favorite=1 OR last_ok IS NOT NULL", (first,))

        # Flagged-language counts per title, and content ratings.
        if "avatar" not in self._columns("profiles"):
            c.execute("ALTER TABLE profiles ADD COLUMN avatar TEXT")
        if "flags" not in self._columns("filters"):
            c.execute("ALTER TABLE filters ADD COLUMN flags TEXT")
        for media_key, data in c.execute("SELECT media_key, data FROM filters WHERE flags IS NULL").fetchall():
            c.execute("UPDATE filters SET flags=? WHERE media_key=?", (json.dumps(_flag_counts(data)), media_key))
        if "tvg_id" not in self._columns("channels"):
            c.execute("ALTER TABLE channels ADD COLUMN tvg_id TEXT")
        if "epg_url" not in self._columns("playlists"):
            c.execute("ALTER TABLE playlists ADD COLUMN epg_url TEXT")
        for table in ("meta", "shows"):
            if "cert" not in self._columns(table):
                c.execute(f"ALTER TABLE {table} ADD COLUMN cert TEXT")

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
            """INSERT INTO filters(media_key,source_id,item_id,title,duration,engine,data,flags,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?)
               ON CONFLICT(media_key) DO UPDATE SET title=excluded.title,
                 duration=excluded.duration, engine=excluded.engine,
                 data=excluded.data, flags=excluded.flags, updated_at=excluded.updated_at""",
            (media_key, source_id, item_id, title, duration, engine,
             json.dumps(ranges), json.dumps(_flag_counts(ranges)), time.time()),
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

    def drop_unknown_sources(self, valid: set[str]) -> int:
        """Forget titles from sources that were removed (a playlist that became Live TV, a deleted share)."""
        with self._lock:
            c = self._conn
            gone = [r[0] for r in c.execute("SELECT media_key FROM library_items WHERE origin NOT IN (%s) AND source_id NOT IN (%s)"
                                            % (",".join("?" * len(valid)) or "''", ",".join("?" * len(valid)) or "''"), (*valid, *valid))]
            for k in gone:
                c.execute("DELETE FROM meta WHERE media_key=?", (k,))
                c.execute("DELETE FROM library_items WHERE media_key=?", (k,))
            c.commit()
        return len(gone)

    def library_stats(self) -> dict[str, int]:
        total = self._one("SELECT COUNT(*) n FROM library_items")["n"]
        scanned = self._one("SELECT COUNT(*) n FROM library_items l JOIN filters f "
                            "ON f.media_key=l.media_key")["n"]
        return {"titles": total, "scanned": scanned}

    def library_version(self) -> str:
        """A cheap fingerprint of everything the library pages show; it changes when a scan, refresh or rename does."""
        r = self._one(
            "SELECT (SELECT COUNT(*) FROM library_items) a, (SELECT COUNT(*) FROM meta) b,"
            " (SELECT COALESCE(MAX(updated_at),0) FROM meta) c, (SELECT COALESCE(MAX(updated_at),0) FROM shows) d,"
            " (SELECT COUNT(*) FROM filters) e, (SELECT COUNT(*) FROM channels) f, (SELECT COUNT(*) FROM playlists) g")
        return ".".join(str(r[k]) for k in "abcdefg")

    def get_probe(self, source_id: str, item_id: str, max_age: float) -> dict | None:
        r = self._one("SELECT data, updated_at FROM probes WHERE source_id=? AND item_id=?", (source_id, item_id))
        if not r or time.time() - r["updated_at"] > max_age:
            return None
        try:
            return json.loads(r["data"])
        except ValueError:
            return None

    def save_probe(self, source_id: str, item_id: str, data: dict) -> None:
        self._exec("INSERT OR REPLACE INTO probes(source_id,item_id,data,updated_at) VALUES(?,?,?,?)",
                   (source_id, item_id, json.dumps(data), time.time()))

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
                "episode", "overview", "genres", "rating", "runtime", "art", "ids", "provider", "cert", "locked"]
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
        cols = ["show_key", "title", "year", "overview", "genres", "rating", "art", "ids", "provider", "cert", "locked"]
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

    def list_movies(self, profile_id: str = "") -> list[dict]:
        rows = self._all("SELECT m.*, (f.media_key IS NOT NULL) AS scanned, f.flags AS flags, p.position, p.duration, "
                         "COALESCE(p.finished,0) AS watched FROM meta m "
                         "LEFT JOIN filters f ON f.media_key=m.media_key "
                         "LEFT JOIN progress p ON p.media_key=m.media_key AND p.profile_id=? WHERE m.kind='movie' "
                         "ORDER BY lower(m.title), m.year", (profile_id,))
        return [self._decode(r) for r in rows]

    def list_shows(self, profile_id: str = "") -> list[dict]:
        rows = self._all(
            "SELECT s.*, COUNT(m.media_key) AS episodes, COUNT(DISTINCT m.season) AS seasons, "
            "SUM(f.media_key IS NOT NULL) AS scanned, SUM(COALESCE(p.finished,0)) AS watched FROM shows s "
            "LEFT JOIN meta m ON m.show_key=s.show_key LEFT JOIN filters f ON f.media_key=m.media_key "
            "LEFT JOIN progress p ON p.media_key=m.media_key AND p.profile_id=? "
            "GROUP BY s.show_key ORDER BY lower(s.title)", (profile_id,))
        return [self._decode(r) for r in rows]

    def episodes_of(self, show_key: str, profile_id: str = "") -> list[dict]:
        rows = self._all("SELECT m.*, (f.media_key IS NOT NULL) AS scanned, f.flags AS flags, p.position, p.duration, "
                         "COALESCE(p.finished,0) AS watched FROM meta m "
                         "LEFT JOIN filters f ON f.media_key=m.media_key "
                         "LEFT JOIN progress p ON p.media_key=m.media_key AND p.profile_id=? WHERE m.show_key=? "
                         "ORDER BY m.season, m.episode", (profile_id, show_key))
        return [self._decode(r) for r in rows]

    def title_facts(self, key: str) -> dict | None:
        """What a kids profile needs to judge one title: its rating and flagged-language counts."""
        return self._one("SELECT m.media_key, m.cert, m.show_key, s.cert AS show_cert, f.flags, (f.media_key IS NOT NULL) AS scanned "
                         "FROM meta m LEFT JOIN filters f ON f.media_key=m.media_key LEFT JOIN shows s ON s.show_key=m.show_key "
                         "WHERE m.media_key=?", (key,))

    def episode_facts(self) -> list[dict]:
        """The same, for every episode (so a show can be judged by its episodes)."""
        return self._all("SELECT m.media_key, m.show_key, m.cert, s.cert AS show_cert, f.flags, (f.media_key IS NOT NULL) AS scanned "
                         "FROM meta m LEFT JOIN filters f ON f.media_key=m.media_key LEFT JOIN shows s ON s.show_key=m.show_key "
                         "WHERE m.kind='episode'")

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

    # ---- playback progress ----------------------------------------------------------------
    MIN_RESUME = 20.0        # earlier than this is "not started"
    FINISHED_AT = 0.92       # past this share of the length (or, in a long title, within 90 s of the end) it counts as watched

    def save_progress(self, profile_id: str, key: str, source_id: str, item_id: str, title: str, position: float,
                      duration: float | None) -> dict:
        position = max(0.0, position)
        duration = duration if duration and duration > 0 else None
        if duration and (position >= duration * self.FINISHED_AT or (duration > 600 and duration - position < 90)):
            state = {"position": 0.0, "finished": 1}
        elif position < self.MIN_RESUME:
            self._exec("DELETE FROM progress WHERE profile_id=? AND media_key=? AND finished=0", (profile_id, key))   # started over
            return {"position": 0.0, "finished": 0}
        else:
            state = {"position": position, "finished": 0}
        self._exec("INSERT INTO progress(profile_id,media_key,source_id,item_id,title,position,duration,finished,updated_at) "
                   "VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(profile_id,media_key) DO UPDATE SET position=excluded.position, "
                   "duration=COALESCE(excluded.duration, duration), finished=excluded.finished, title=excluded.title, "
                   "updated_at=excluded.updated_at",
                   (profile_id, key, source_id, item_id, title, state["position"], duration, state["finished"], time.time()))
        return state

    def get_progress(self, profile_id: str, key: str) -> dict | None:
        return self._one("SELECT * FROM progress WHERE profile_id=? AND media_key=?", (profile_id, key))

    def progress_map(self, profile_id: str, keys: list[str]) -> dict[str, dict]:
        if not keys:
            return {}
        out = {}
        for i in range(0, len(keys), 500):
            chunk = keys[i:i + 500]
            for r in self._all(f"SELECT * FROM progress WHERE profile_id=? AND media_key IN ({','.join('?' * len(chunk))})",
                               (profile_id, *chunk)):
                out[r["media_key"]] = r
        return out

    def recent_progress(self, profile_id: str, limit: int = 20) -> list[dict]:
        return self._all("SELECT * FROM progress WHERE profile_id=? AND finished=0 AND position>=? ORDER BY updated_at DESC LIMIT ?",
                         (profile_id, self.MIN_RESUME, limit))

    def clear_progress(self, profile_id: str, key: str) -> None:
        self._exec("DELETE FROM progress WHERE profile_id=? AND media_key=?", (profile_id, key))

    # ---- profiles ----------------------------------------------------------------------
    def _profile(self, r: dict | None) -> dict | None:
        if r:
            r["kids"] = bool(r["kids"])
            r["settings"] = json.loads(r["settings"]) if r.get("settings") else {}
        return r

    def list_profiles(self) -> list[dict]:
        return [self._profile(r) for r in self._all("SELECT * FROM profiles ORDER BY position, created_at")]

    def get_profile(self, pid: str) -> dict | None:
        return self._profile(self._one("SELECT * FROM profiles WHERE id=?", (pid,)))

    def save_profile(self, pid: str, name: str, kids: bool, color: str, settings: dict, avatar: str = "") -> None:
        pos = self._one("SELECT COALESCE(MAX(position), -1) + 1 AS n FROM profiles")["n"]
        self._exec("INSERT INTO profiles(id,name,kids,color,avatar,settings,position,created_at) VALUES(?,?,?,?,?,?,?,?) "
                   "ON CONFLICT(id) DO UPDATE SET name=excluded.name, kids=excluded.kids, color=excluded.color, "
                   "avatar=excluded.avatar, settings=excluded.settings",
                   (pid, name, int(kids), color, avatar or "", json.dumps(settings), pos, time.time()))

    def delete_profile(self, pid: str) -> None:
        for sql in ("DELETE FROM progress WHERE profile_id=?", "DELETE FROM channel_marks WHERE profile_id=?",
                    "DELETE FROM profiles WHERE id=?"):
            self._exec(sql, (pid,))

    # ---- live TV ------------------------------------------------------------------------
    def list_playlists(self) -> list[dict]:
        return self._all("SELECT * FROM playlists ORDER BY name")

    def get_playlist(self, pid: str) -> dict | None:
        return self._one("SELECT * FROM playlists WHERE id=?", (pid,))

    def save_playlist(self, pid: str, name: str, url: str) -> None:
        self._exec("INSERT INTO playlists(id,name,url) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name, url=excluded.url",
                   (pid, name, url))

    def set_playlist_epg(self, pid: str, urls: list[str]) -> None:
        self._exec("UPDATE playlists SET epg_url=? WHERE id=?", (",".join(urls), pid))

    def epg_urls(self) -> list[str]:
        return [u for r in self._all("SELECT epg_url FROM playlists WHERE epg_url IS NOT NULL AND epg_url != ''")
                for u in r["epg_url"].split(",") if u]

    def replace_programmes(self, rows: list[tuple]) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM programmes")
            self._conn.executemany("INSERT INTO programmes(tvg_id,start,stop,title,descr) VALUES(?,?,?,?,?)", rows)
            self._conn.commit()

    def epg_now_next(self, keys: list[str], now: float | None = None) -> dict[str, dict]:
        """{chan_key: {"now": {...}, "next": {...}}} for the channels that have guide data."""
        now = now or time.time()
        if not keys:
            return {}
        marks = ",".join("?" * len(keys))
        rows = self._all(
            f"SELECT c.chan_key k, p.title, p.descr, p.start, p.stop FROM channels c JOIN programmes p ON p.tvg_id=c.tvg_id "
            f"WHERE c.chan_key IN ({marks}) AND p.stop>? ORDER BY p.start", (*keys, now))
        out: dict[str, dict] = {}
        for r in rows:
            slot = out.setdefault(r["k"], {})
            item = {"title": r["title"], "desc": r["descr"], "start": r["start"], "stop": r["stop"]}
            if "now" not in slot and r["start"] <= now:
                slot["now"] = item
            elif "next" not in slot and r["start"] > now:
                slot["next"] = item
        return out

    def playlist_status(self, pid: str, count: int | None, error: str | None) -> None:
        self._exec("UPDATE playlists SET channels=COALESCE(?,channels), updated_at=?, error=? WHERE id=?",
                   (count, time.time(), error, pid))

    def delete_playlist(self, pid: str) -> None:
        self._exec("DELETE FROM channels WHERE playlist=?", (pid,))
        self._exec("DELETE FROM playlists WHERE id=?", (pid,))

    def replace_channels(self, pid: str, rows: list[tuple]) -> int:
        """rows = (chan_key, name, grp, logo, url, item_id). Failure counts of channels that are still in the
        list are kept (favorites live in channel_marks, per profile). Returns the channel count."""
        with self._lock:
            c = self._conn
            keep = {r[0]: r[1] for r in c.execute("SELECT chan_key, failures FROM channels WHERE playlist=?", (pid,))}
            c.execute("DELETE FROM channels WHERE playlist=?", (pid,))
            c.executemany(
                "INSERT OR REPLACE INTO channels(chan_key,playlist,name,letter,grp,logo,url,item_id,position,failures,tvg_id) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                [(r[0], pid, r[1], letter_of(r[1]), r[2], r[3], r[4], r[5], pos, keep.get(r[0], 0), r[6] if len(r) > 6 else "")
                 for pos, r in enumerate(rows)])
            c.commit()
        return len(rows)

    @staticmethod
    def _channel_filter(profile_id: str, q: str, group: str, favorites: bool, hide_dead: bool, letter: str = "", recent: bool = False):
        sql = ["FROM channels c LEFT JOIN channel_marks m ON m.chan_key=c.chan_key AND m.profile_id=? WHERE 1=1"]
        args: list = [profile_id]
        if q:
            sql.append("AND c.name LIKE ?"); args.append(f"%{q}%")
        if group:
            sql.append("AND c.grp LIKE ?"); args.append(f"%;{group};%")
        if letter:
            sql.append("AND c.letter=?"); args.append(letter)
        if favorites:
            sql.append("AND COALESCE(m.favorite,0)=1")
        if recent:
            sql.append("AND m.last_ok IS NOT NULL")
        if hide_dead:
            sql.append("AND c.failures<2")
        return " ".join(sql), args

    def list_channels(self, q: str = "", group: str = "", favorites: bool = False, hide_dead: bool = True,
                      limit: int = 120, offset: int = 0, letter: str = "", recent: bool = False, profile_id: str = "") -> list[dict]:
        frm, args = self._channel_filter(profile_id, q, group, favorites, hide_dead, letter, recent)
        order = "m.last_ok DESC" if recent else "lower(c.name), c.position"
        return self._all(f"SELECT c.*, COALESCE(m.favorite,0) AS favorite, m.last_ok AS last_ok {frm} ORDER BY {order} LIMIT ? OFFSET ?",
                         (*args, limit, offset))

    def count_channels(self, q: str = "", group: str = "", favorites: bool = False, hide_dead: bool = True,
                       letter: str = "", recent: bool = False, profile_id: str = "") -> int:
        frm, args = self._channel_filter(profile_id, q, group, favorites, hide_dead, letter, recent)
        return self._one(f"SELECT COUNT(*) n {frm}", tuple(args))["n"]

    def letter_counts(self, q: str = "", group: str = "", favorites: bool = False, hide_dead: bool = True,
                      profile_id: str = "") -> dict[str, int]:
        """How many channels start with each letter, under the current filters (but not the letter itself)."""
        frm, args = self._channel_filter(profile_id, q, group, favorites, hide_dead)
        return {r["letter"]: r["n"] for r in self._all(
            f"SELECT c.letter AS letter, COUNT(*) n {frm} GROUP BY c.letter", tuple(args)) if r["letter"]}

    def channel_groups(self) -> list[dict]:
        counts: dict[str, int] = {}
        for r in self._all("SELECT grp FROM channels WHERE failures<2"):
            for g in (r["grp"] or "").split(";"):
                if g:
                    counts[g] = counts.get(g, 0) + 1
        return [{"name": g, "count": n} for g, n in sorted(counts.items(), key=lambda kv: kv[0].lower())]

    def channel_stats(self, profile_id: str = "") -> dict:
        r = self._one("SELECT COUNT(*) total, SUM(c.failures>=2) dead, SUM(COALESCE(m.favorite,0)=1) favorites FROM channels c "
                      "LEFT JOIN channel_marks m ON m.chan_key=c.chan_key AND m.profile_id=?", (profile_id,))
        return {"total": r["total"] or 0, "dead": r["dead"] or 0, "favorites": r["favorites"] or 0}

    def get_channel(self, key: str) -> dict | None:
        return self._one("SELECT * FROM channels WHERE chan_key=?", (key,))

    def set_favorite(self, key: str, on: bool, profile_id: str = "") -> None:
        self._exec("INSERT INTO channel_marks(profile_id,chan_key,favorite) VALUES(?,?,?) "
                   "ON CONFLICT(profile_id,chan_key) DO UPDATE SET favorite=excluded.favorite", (profile_id, key, int(on)))

    def report_channel(self, key: str, ok: bool, profile_id: str = "") -> None:
        if ok:
            self._exec("UPDATE channels SET failures=0 WHERE chan_key=?", (key,))
            self._exec("INSERT INTO channel_marks(profile_id,chan_key,last_ok) VALUES(?,?,?) "
                       "ON CONFLICT(profile_id,chan_key) DO UPDATE SET last_ok=excluded.last_ok", (profile_id, key, time.time()))
        else:
            self._exec("UPDATE channels SET failures=failures+1 WHERE chan_key=?", (key,))

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
