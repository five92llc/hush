"""qBittorrent: a window onto the client you already run (its downloads and its RSS downloader).

Hush only talks to qBittorrent's web interface. What gets downloaded, and where it is saved, is decided
by qBittorrent and your own RSS rules; Hush shows progress, lets you pause or resume, and refreshes the library
when something finishes.
"""
from __future__ import annotations

import logging
import threading
import time
from urllib.parse import urlparse

import httpx

log = logging.getLogger("hush.qbit")
DONE_STATES = {"uploading", "stalledUP", "pausedUP", "stoppedUP", "queuedUP", "checkingUP", "forcedUP"}


class QbitError(Exception):
    pass


class Qbit:
    def __init__(self, db, on_finished=None, transport=None):
        self.db = db
        self.transport = transport              # tests supply a fake qBittorrent here
        self.on_finished = on_finished          # called with the names of torrents that just finished
        self._http: httpx.Client | None = None
        self._base = ""
        self._lock = threading.Lock()

    # ---- settings ------------------------------------------------------------------------
    def settings(self) -> dict:
        return {"url": "", "username": "", "password": "", **self.db.get_setting("qbit", {})}

    def public(self) -> dict:
        s = self.settings()
        return {"url": s["url"], "username": s["username"], "has_password": bool(s["password"]), "configured": bool(s["url"])}

    def update(self, patch: dict) -> dict:
        s = self.settings()
        if "url" in patch:
            url = str(patch["url"]).strip().rstrip("/")
            if url and urlparse(url).scheme not in ("http", "https"):
                raise QbitError("The address starts with http:// or https://, for example http://192.168.1.20:8080")
            s["url"] = url
        if "username" in patch:
            s["username"] = str(patch["username"]).strip()
        if patch.get("password"):                 # left blank = keep the saved one
            s["password"] = str(patch["password"])
        self.db.set_setting("qbit", s)
        self._http = None
        return self.public()

    # ---- connection ------------------------------------------------------------------------
    def _client(self) -> httpx.Client:
        s = self.settings()
        if not s["url"]:
            raise QbitError("qBittorrent is not set up yet")
        with self._lock:
            if self._http is None or self._base != s["url"]:
                http = httpx.Client(base_url=s["url"], timeout=10, headers={"Referer": s["url"]}, transport=self.transport)
                try:
                    r = http.post("/api/v2/auth/login", data={"username": s["username"], "password": s["password"]})
                except httpx.HTTPError as exc:
                    raise QbitError(f"Could not reach qBittorrent at {s['url']}: {exc}") from exc
                # Older versions answer 200 "Ok." / "Fails."; qBittorrent 5.2 answers 204 with a session cookie.
                ok = r.status_code in (200, 204) and r.text.strip() != "Fails." and (r.text.strip() == "Ok." or bool(http.cookies))
                if r.status_code == 403 and "banned" in r.text.lower():
                    raise QbitError("qBittorrent has temporarily banned Hush's address after failed logins. "
                                    "Wait a while, or restart qBittorrent, then try again.")
                if not ok:
                    raise QbitError("qBittorrent refused the login. Check the user name and password, and that "
                                    "'Web User Interface' is switched on in its options.")
                self._http, self._base = http, s["url"]
            return self._http

    def _call(self, method: str, path: str, **kw):
        for attempt in (0, 1):
            http = self._client()
            try:
                r = http.request(method, f"/api/v2/{path}", **kw)
            except httpx.HTTPError as exc:
                self._http = None
                raise QbitError(f"qBittorrent did not answer: {exc}") from exc
            if r.status_code == 403 and attempt == 0:         # the session expired: log in again
                self._http = None
                continue
            return r
        raise QbitError("qBittorrent logged us out")

    # ---- what it knows ---------------------------------------------------------------------
    def version(self) -> str:
        r = self._call("GET", "app/version")
        r.raise_for_status()
        return r.text.strip()

    def torrents(self) -> list[dict]:
        r = self._call("GET", "torrents/info", params={"sort": "added_on", "reverse": "true", "limit": 100})
        r.raise_for_status()
        out = []
        for t in r.json():
            out.append({"hash": t["hash"], "name": t["name"], "progress": t.get("progress", 0), "state": t.get("state", ""),
                        "size": t.get("size", 0), "dlspeed": t.get("dlspeed", 0), "upspeed": t.get("upspeed", 0), "eta": t.get("eta", 0),
                        "category": t.get("category", ""), "added_on": t.get("added_on", 0), "completion_on": t.get("completion_on", 0),
                        "done": t.get("progress", 0) >= 1 or t.get("state") in DONE_STATES,
                        "paused": str(t.get("state", "")).startswith(("paused", "stopped"))})
        return out

    def act(self, h: str, action: str) -> None:
        if not h.isalnum():
            raise QbitError("Bad torrent")
        if action == "pause":
            for p in ("torrents/stop", "torrents/pause"):               # qBittorrent 5 renamed pause to stop
                if self._call("POST", p, data={"hashes": h}).status_code != 404:
                    return
        elif action == "resume":
            for p in ("torrents/start", "torrents/resume"):
                if self._call("POST", p, data={"hashes": h}).status_code != 404:
                    return
        elif action == "remove":                                          # takes it off the list; the files stay
            self._call("POST", "torrents/delete", data={"hashes": h, "deleteFiles": "false"})
        else:
            raise QbitError("Unknown action")

    def rss(self) -> dict:
        """The feeds qBittorrent follows (with their latest items) and the download rules it applies."""
        feeds = []
        r = self._call("GET", "rss/items", params={"withData": "true"})
        if r.status_code == 200:
            for name, feed in (r.json() or {}).items():
                if not isinstance(feed, dict):
                    continue
                articles = sorted(feed.get("articles", []), key=lambda a: a.get("date", ""), reverse=True)[:15]
                feeds.append({"name": name, "url": feed.get("url", ""), "title": feed.get("title") or name, "has_error": bool(feed.get("hasError")),
                              "loading": bool(feed.get("isLoading")), "last_build": feed.get("lastBuildDate", ""),
                              "articles": [{"title": a.get("title", ""), "date": a.get("date", ""), "read": bool(a.get("isRead"))} for a in articles]})
        rules = []
        r = self._call("GET", "rss/rules")
        if r.status_code == 200:
            for name, rule in (r.json() or {}).items():
                rules.append({"name": name, "enabled": bool(rule.get("enabled")), "must_contain": rule.get("mustContain", ""),
                              "feeds": rule.get("affectedFeeds", []), "category": rule.get("assignedCategory", ""),
                              "last_match": rule.get("lastMatch", "")})
        return {"feeds": feeds, "rules": rules}

    def refresh_feed(self, path: str) -> None:
        self._call("POST", "rss/refreshItem", data={"itemPath": path})

    # ---- noticing finished downloads -----------------------------------------------------------
    def watch(self) -> None:
        threading.Thread(target=self._loop, name="qbit-watch", daemon=True).start()

    def _loop(self) -> None:
        time.sleep(45)
        while True:
            try:
                if self.settings()["url"]:
                    self.check_finished()
            except Exception as exc:  # noqa: BLE001 - qBittorrent being off must never matter
                log.debug("qbit check: %s", exc)
            time.sleep(60)

    def check_finished(self) -> list[str]:
        done = {t["hash"]: t["name"] for t in self.torrents() if t["done"]}
        seen = self.db.get_setting("qbit_seen", None)
        self.db.set_setting("qbit_seen", sorted(done))
        if seen is None:                         # first look: what was already finished is not news
            return []
        new = [n for h, n in done.items() if h not in set(seen)]
        if new and self.on_finished:
            self.on_finished(new)
        return new
