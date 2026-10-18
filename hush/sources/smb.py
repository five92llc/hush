"""SMB / CIFS shares (Windows shares, Synology, TrueNAS, QNAP...) via smbprotocol.

No OS mount is needed. Files are read with random access so seeking and range
requests work over the network.
"""
from __future__ import annotations

import ntpath
import threading

from .base import Entry, MediaRef, Source, SourceError, SUB_EXT, classify, dec, enc, sort_entries

try:
    import smbclient  # type: ignore
except ImportError:  # pragma: no cover
    smbclient = None


class SMBSource(Source):
    type = "smb"
    _session_lock = threading.Lock()

    def __init__(self, conf):
        super().__init__(conf)
        if smbclient is None:
            raise SourceError("smbprotocol is not installed")
        self.server = conf["server"]
        self.share = conf["share"].strip("\\/")
        self.base = (conf.get("path") or "").strip("\\/").replace("/", "\\")
        self.username = conf.get("username") or None
        self.password = conf.get("password") or None
        self.port = int(conf.get("port", 445))
        self._registered = False
        # Passed on every call so a non-default port / credentials are always used.
        self._kw = {"port": self.port, "username": self.username, "password": self.password}

    def _session(self):
        with self._session_lock:
            if not self._registered:
                try:
                    smbclient.register_session(self.server, username=self.username,
                                               password=self.password, port=self.port,
                                               encrypt=self.conf.get("encrypt"))
                except Exception as exc:  # noqa: BLE001
                    raise SourceError(f"SMB connect failed: {exc}") from exc
                self._registered = True

    def _unc(self, rel: str) -> str:
        parts = [p for p in (self.base, rel.replace("/", "\\")) if p]
        if any(seg == ".." for p in parts for seg in p.split("\\")):
            raise SourceError("bad path")
        return f"\\\\{self.server}\\{self.share}" + "".join("\\" + p for p in parts)

    def browse(self, dir_id: str = "") -> list[Entry]:
        self._session()
        rel = dec(dir_id) if dir_id else ""
        out: list[Entry] = []
        try:
            for de in smbclient.scandir(self._unc(rel), **self._kw):
                if de.name.startswith("."):
                    continue
                child = f"{rel}\\{de.name}" if rel else de.name
                # Use the info returned by the directory listing itself: no extra round trips.
                info = de.smb_info
                if info.file_attributes & 0x10:          # FILE_ATTRIBUTE_DIRECTORY
                    out.append(Entry(enc(child), de.name, "dir"))
                else:
                    kind = classify(de.name)
                    if kind:
                        out.append(Entry(enc(child), de.name, kind, size=info.end_of_file))
        except SourceError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise SourceError(f"SMB browse failed: {exc}") from exc
        return sort_entries(out)

    def resolve(self, item_id: str) -> MediaRef:
        self._session()
        rel = dec(item_id)
        unc = self._unc(rel)
        try:
            size = smbclient.stat(unc, **self._kw).st_size
        except Exception as exc:  # noqa: BLE001
            raise SourceError(f"SMB file not found: {exc}") from exc
        name = ntpath.basename(unc)
        stem = name.rsplit(".", 1)[0]

        # Sidecar subtitles in the same folder (used for fast analysis).
        sub_openers = []
        folder = ntpath.dirname(unc)
        try:
            for de in smbclient.scandir(folder, **self._kw):
                low = de.name.lower()
                if low.startswith(stem.lower()) and any(low.endswith(e) for e in SUB_EXT):
                    p = ntpath.join(folder, de.name)
                    sub_openers.append(lambda p=p: smbclient.open_file(p, mode="rb", **self._kw))
        except Exception:  # noqa: BLE001
            pass

        return MediaRef(
            title=stem, kind=classify(name) or "video", size=size, name=name,
            opener=lambda: smbclient.open_file(unc, mode="rb", **self._kw),
            subtitle_openers=sub_openers,
        )
