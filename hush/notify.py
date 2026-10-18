"""Optional webhook notifications (ntfy, Gotify, Home Assistant, Discord-style webhooks...)."""
from __future__ import annotations

import logging
import threading

import httpx

from .sources.base import SourceError
from .sources.http import check_url_allowed

log = logging.getLogger("hush.notify")
DEFAULTS = {"url": "", "format": "text", "on_scans_done": True, "on_failure": True, "last_error": ""}


class Notifier:
    def __init__(self, db):
        self.db = db

    def config(self) -> dict:
        return {**DEFAULTS, **self.db.get_setting("notify", {})}

    def update(self, patch: dict) -> dict:
        conf = self.config()
        if "url" in patch:
            url = str(patch["url"]).strip()
            if url:
                check_url_allowed(url)           # http(s) only, no link-local addresses
            conf["url"] = url
        if patch.get("format") in ("text", "json"):
            conf["format"] = patch["format"]
        for k in ("on_scans_done", "on_failure"):
            if k in patch:
                conf[k] = bool(patch[k])
        self.db.set_setting("notify", conf)
        return conf

    def _post(self, conf: dict, title: str, message: str) -> None:
        if conf["format"] == "json":
            r = httpx.post(conf["url"], json={"title": title, "message": message, "text": f"{title}: {message}"},
                           timeout=10, follow_redirects=True)
        else:   # plain text body with a Title header: what ntfy and Gotify's simple endpoints expect
            r = httpx.post(conf["url"], content=message.encode(), headers={"Title": title},
                           timeout=10, follow_redirects=True)
        r.raise_for_status()

    def test(self) -> None:
        conf = self.config()
        if not conf["url"]:
            raise SourceError("Add a webhook address first")
        check_url_allowed(conf["url"])
        try:
            self._post(conf, "Hush", "This is a test notification.")
        except httpx.HTTPError as exc:
            raise SourceError(f"The webhook did not accept it: {exc}") from exc

    def event(self, kind: str, title: str, message: str) -> None:
        """Send in the background; a broken webhook must never disturb a scan."""
        conf = self.config()
        if not conf["url"] or not conf.get(f"on_{kind}", True):
            return

        def go() -> None:
            err = ""
            try:
                check_url_allowed(conf["url"])
                self._post(conf, title, message)
            except Exception as exc:  # noqa: BLE001
                err = str(exc)[:200]
                log.warning("notification failed: %s", err)
            if err != conf["last_error"]:
                self.db.set_setting("notify", {**self.config(), "last_error": err})

        threading.Thread(target=go, name="notify", daemon=True).start()
