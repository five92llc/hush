"""Source registry: builds Source objects from config + runtime-added sources."""
from __future__ import annotations

import re
import threading
from typing import Any

from .base import Entry, MediaRef, Source, SourceError, media_key  # noqa: F401
from .dlna import DLNASource, discover as discover_dlna  # noqa: F401
from .http import HTTPSource
from .local import LocalSource
from .mediaservers import JellyfinSource, PlexSource
from .smb import SMBSource

TYPES: dict[str, type[Source]] = {
    "local": LocalSource, "smb": SMBSource, "http": HTTPSource,
    "dlna": DLNASource, "jellyfin": JellyfinSource, "plex": PlexSource,
}

# Fields never sent back to the browser.
SECRET_FIELDS = {"password", "api_key", "token", "headers"}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "source"


class Registry:
    def __init__(self, static: list[dict[str, Any]], db):
        self.db = db
        self._lock = threading.Lock()
        self._sources: dict[str, Source] = {}
        self.errors: dict[str, str] = {}
        # Built-in source for ad-hoc "Open URL" playback.
        self._add({"id": "url", "type": "http", "name": "Opened URLs"})
        for conf in static:
            self._add(dict(conf))
        for conf in db.list_sources():
            self._add({**conf, "_runtime": True})

    def _add(self, conf: dict[str, Any]) -> None:
        conf.setdefault("id", slug(conf.get("name") or conf.get("type", "src")))
        cls = TYPES.get(conf.get("type", ""))
        if not cls:
            self.errors[conf["id"]] = f"unknown source type {conf.get('type')!r}"
            return
        try:
            self._sources[conf["id"]] = cls(conf)
            self.errors.pop(conf["id"], None)
        except Exception as exc:  # noqa: BLE001
            self.errors[conf["id"]] = str(exc)

    def get(self, source_id: str) -> Source:
        src = self._sources.get(source_id)
        if not src:
            raise SourceError(self.errors.get(source_id, f"unknown source {source_id}"))
        return src

    def list(self) -> list[dict[str, Any]]:
        out = [s.info() for sid, s in self._sources.items() if sid != "url"]
        out += [{"id": k, "name": k, "type": "?", "error": v} for k, v in self.errors.items()]
        return out

    def add_runtime(self, conf: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            conf = {k: v for k, v in conf.items() if not k.startswith("_")}
            base = slug(conf.get("name") or conf.get("type", "src"))
            sid, n = base, 2
            while sid in self._sources or sid == "url":
                sid, n = f"{base}-{n}", n + 1
            conf["id"] = sid
            cls = TYPES.get(conf.get("type", ""))
            if not cls:
                raise SourceError("unknown source type")
            src = cls({**conf, "_runtime": True})  # validates config
            self._sources[sid] = src
            self.db.save_source(conf)
            return src.info()

    def remove_runtime(self, source_id: str) -> None:
        src = self.get(source_id)
        if not src.conf.get("_runtime"):
            raise SourceError("sources from config.yaml can only be removed there")
        self._sources.pop(source_id, None)
        self.db.delete_source(source_id)
