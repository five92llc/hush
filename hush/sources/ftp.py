"""Plain FTP servers (routers, NAS boxes, seedboxes).

Browsing uses ftplib. Playback hands ffmpeg the ``ftp://`` address itself, which
supports seeking, so scanning and filtering work like any other file.
"""
from __future__ import annotations

import ftplib
import posixpath
from urllib.parse import quote

from .base import Entry, MediaRef, Source, SourceError, classify, dec, enc, sort_entries


def safe_rel(rel: str) -> str:
    parts = [p for p in rel.replace("\\", "/").split("/") if p]
    if ".." in parts:
        raise SourceError("bad path")
    return "/".join(parts)


class FTPSource(Source):
    type = "ftp"

    def __init__(self, conf):
        super().__init__(conf)
        self.host = conf["host"]
        self.port = int(conf.get("port", 21))
        self.username = conf.get("username") or "anonymous"
        self.password = conf.get("password") or "anonymous@"
        self.base = safe_rel(conf.get("path") or "")

    def _connect(self) -> ftplib.FTP:
        try:
            ftp = ftplib.FTP()
            ftp.connect(self.host, self.port, timeout=15)
            ftp.login(self.username, self.password)
            return ftp
        except (OSError, ftplib.Error) as exc:
            raise SourceError(f"FTP connect failed: {exc}") from exc

    def _full(self, rel: str) -> str:
        return "/" + "/".join(p for p in (self.base, safe_rel(rel)) if p)

    def browse(self, dir_id: str = "") -> list[Entry]:
        rel = safe_rel(dec(dir_id)) if dir_id else ""
        ftp = self._connect()
        out: list[Entry] = []
        try:
            try:
                for name, facts in ftp.mlsd(self._full(rel), facts=["type", "size"]):
                    kind_fact = facts.get("type", "")
                    if name.startswith(".") or kind_fact in ("cdir", "pdir"):
                        continue
                    child = f"{rel}/{name}" if rel else name
                    if kind_fact == "dir":
                        out.append(Entry(enc(child), name, "dir"))
                    elif (kind := classify(name)):
                        size = int(facts["size"]) if facts.get("size", "").isdigit() else None
                        out.append(Entry(enc(child), name, kind, size=size))
            except ftplib.error_perm:  # no MLSD: fall back to parsing a Unix-style LIST
                lines: list[str] = []
                ftp.cwd(self._full(rel))
                ftp.retrlines("LIST", lines.append)
                for line in lines:
                    cols = line.split(None, 8)
                    if len(cols) < 9 or cols[8].startswith("."):
                        continue
                    name = cols[8].split(" -> ")[0]
                    child = f"{rel}/{name}" if rel else name
                    if line.startswith("d"):
                        out.append(Entry(enc(child), name, "dir"))
                    elif (kind := classify(name)):
                        out.append(Entry(enc(child), name, kind,
                                         size=int(cols[4]) if cols[4].isdigit() else None))
        except (OSError, ftplib.Error) as exc:
            raise SourceError(f"FTP browse failed: {exc}") from exc
        finally:
            try:
                ftp.quit()
            except Exception:  # noqa: BLE001
                pass
        return sort_entries(out)

    def resolve(self, item_id: str) -> MediaRef:
        rel = safe_rel(dec(item_id))
        if not rel:
            raise SourceError("not a file")
        path = self._full(rel)
        ftp = self._connect()
        try:
            ftp.voidcmd("TYPE I")
            size = ftp.size(path)
        except (OSError, ftplib.Error) as exc:
            raise SourceError(f"FTP file not found: {exc}") from exc
        finally:
            try:
                ftp.quit()
            except Exception:  # noqa: BLE001
                pass
        name = posixpath.basename(path)
        auth = f"{quote(self.username, safe='')}:{quote(self.password, safe='')}@"
        url = f"ftp://{auth}{self.host}:{self.port}{quote(path)}"
        return MediaRef(title=name.rsplit(".", 1)[0], kind=classify(name) or "video", url=url,
                        native=True, size=size, name=name)
