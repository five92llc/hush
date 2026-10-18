"""Jellyfin / Emby and Plex libraries.

Both are read through their HTTP APIs and play the *original* file (static
stream), so Hush does its own transcoding and filtering. Embedded subtitle
tracks in the original file are available to the analyzer.
"""
from __future__ import annotations

import httpx

from .base import Entry, MediaRef, Source, SourceError, classify

# ---------------------------------------------------------------- Jellyfin
JF_DIR_TYPES = {"CollectionFolder", "Folder", "UserView", "Series", "Season", "BoxSet",
                "MusicAlbum", "MusicArtist", "Playlist", "PhotoAlbum"}
JF_VIDEO = {"Movie", "Episode", "Video", "MusicVideo", "Trailer"}
JF_AUDIO = {"Audio", "AudioBook"}


class JellyfinSource(Source):
    type = "jellyfin"

    def __init__(self, conf):
        super().__init__(conf)
        self.base = conf["url"].rstrip("/")
        self.headers = {"X-Emby-Token": conf["api_key"],
                        "Authorization": f'MediaBrowser Token="{conf["api_key"]}"'}
        self.user_id = conf.get("user_id")
        self.username = conf.get("username")
        self.verify = conf.get("verify_tls", True)

    def _get(self, path: str, **params):
        try:
            r = httpx.get(self.base + path, headers=self.headers, params=params,
                          timeout=15, verify=self.verify)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SourceError(f"Jellyfin request failed: {exc}") from exc

    def _uid(self) -> str:
        if not self.user_id:
            users = self._get("/Users")
            match = [u for u in users if not self.username or u["Name"] == self.username]
            if not match:
                raise SourceError("Jellyfin user not found")
            self.user_id = match[0]["Id"]
        return self.user_id

    def browse(self, dir_id: str = "") -> list[Entry]:
        uid = self._uid()
        if not dir_id:
            data = self._get(f"/Users/{uid}/Views")
        else:
            data = self._get(f"/Users/{uid}/Items", ParentId=dir_id, SortBy="SortName",
                             Fields="MediaSources,Path", SortOrder="Ascending")
        out = []
        for it in data.get("Items", []):
            t = it.get("Type")
            if it.get("IsFolder") or t in JF_DIR_TYPES:
                out.append(Entry(it["Id"], it["Name"], "dir"))
            elif t in JF_VIDEO or t in JF_AUDIO:
                name = it["Name"]
                if t == "Episode" and it.get("IndexNumber") is not None:
                    name = f"{it['IndexNumber']:02d}. {name}"
                out.append(Entry(it["Id"], name, "audio" if t in JF_AUDIO else "video",
                                 meta={"year": it.get("ProductionYear")}))
        return out

    def resolve(self, item_id: str) -> MediaRef:
        it = self._get(f"/Users/{self._uid()}/Items/{item_id}")
        kind = "audio" if it.get("Type") in JF_AUDIO else "video"
        src = (it.get("MediaSources") or [{}])[0]
        path = src.get("Path") or it.get("Path") or ""
        name = path.replace("\\", "/").rsplit("/", 1)[-1] or f"{it['Name']}.{src.get('Container', 'mkv')}"
        endpoint = "Audio" if kind == "audio" else "Videos"
        url = f"{self.base}/{endpoint}/{item_id}/stream?static=true&MediaSourceId={src.get('Id', item_id)}"
        return MediaRef(title=it["Name"], kind=kind, url=url, headers=dict(self.headers),
                        name=name, size=src.get("Size"))


# ---------------------------------------------------------------- Plex
PLEX_DIRS = {"show", "season", "artist", "album", "collection", "playlist"}
PLEX_VIDEO = {"movie", "episode", "clip"}
PLEX_AUDIO = {"track"}


class PlexSource(Source):
    type = "plex"

    def __init__(self, conf):
        super().__init__(conf)
        self.base = conf["url"].rstrip("/")
        self.headers = {"X-Plex-Token": conf["token"], "Accept": "application/json",
                        "X-Plex-Client-Identifier": "hush-player", "X-Plex-Product": "Hush"}
        self.verify = conf.get("verify_tls", True)

    def _get(self, path: str):
        try:
            r = httpx.get(self.base + path, headers=self.headers, timeout=15, verify=self.verify)
            r.raise_for_status()
            return r.json().get("MediaContainer", {})
        except (httpx.HTTPError, ValueError) as exc:
            raise SourceError(f"Plex request failed: {exc}") from exc

    def browse(self, dir_id: str = "") -> list[Entry]:
        if not dir_id:
            mc = self._get("/library/sections")
            return [Entry(f"section:{d['key']}", d["title"], "dir")
                    for d in mc.get("Directory", []) if d.get("type") in ("movie", "show", "artist")]
        if dir_id.startswith("section:"):
            mc = self._get(f"/library/sections/{dir_id.split(':', 1)[1]}/all")
        else:
            mc = self._get(f"/library/metadata/{dir_id}/children")
        out = []
        for m in mc.get("Metadata", []) + mc.get("Directory", []):
            t = m.get("type")
            if t in PLEX_DIRS:
                out.append(Entry(m["ratingKey"], m["title"], "dir"))
            elif t in PLEX_VIDEO or t in PLEX_AUDIO:
                name = m["title"]
                if t == "episode" and m.get("index") is not None:
                    name = f"{m['index']:02d}. {name}"
                out.append(Entry(m["ratingKey"], name, "audio" if t in PLEX_AUDIO else "video",
                                 meta={"year": m.get("year")}))
        return out

    def resolve(self, item_id: str) -> MediaRef:
        mc = self._get(f"/library/metadata/{item_id}")
        meta = (mc.get("Metadata") or [None])[0]
        if not meta:
            raise SourceError("Plex item not found")
        try:
            part = meta["Media"][0]["Part"][0]
        except (KeyError, IndexError):
            raise SourceError("Plex item has no media part")
        name = (part.get("file") or "").replace("\\", "/").rsplit("/", 1)[-1] \
            or f"{meta['title']}.{part.get('container', 'mkv')}"
        kind = "audio" if meta.get("type") in PLEX_AUDIO else (classify(name) or "video")
        return MediaRef(title=meta["title"], kind=kind, url=self.base + part["key"],
                        headers={"X-Plex-Token": self.headers["X-Plex-Token"]},
                        name=name, size=part.get("size"))
