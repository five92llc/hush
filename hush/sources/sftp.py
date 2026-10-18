"""SFTP (SSH file transfer): Linux servers, seedboxes, anything with SSH.

Files are read with random access through paramiko and served to ffmpeg over
the same authenticated loopback endpoint SMB uses, so seeking works.
"""
from __future__ import annotations

import posixpath
import stat
import threading

from .base import Entry, MediaRef, Source, SourceError, classify, dec, enc, sort_entries
from .ftp import safe_rel

try:
    import paramiko  # type: ignore
except ImportError:  # pragma: no cover
    paramiko = None


class SFTPSource(Source):
    type = "sftp"

    def __init__(self, conf):
        super().__init__(conf)
        if paramiko is None:
            raise SourceError("paramiko is not installed (pip install paramiko)")
        self.host = conf["host"]
        self.port = int(conf.get("port", 22))
        self.username = conf.get("username") or None
        self.password = conf.get("password") or None
        self.key_file = conf.get("key_file") or None
        self.base = safe_rel(conf.get("path") or "")
        self._lock = threading.Lock()
        self._ssh = None
        self._sftp = None

    def _client(self):
        with self._lock:
            if self._sftp is not None and self._ssh.get_transport() and self._ssh.get_transport().is_active():
                return self._sftp
            self.close()
            ssh = paramiko.SSHClient()
            # Home-network convenience: trust the host key on first use, without pinning it.
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                ssh.connect(self.host, port=self.port, username=self.username, password=self.password,
                            key_filename=self.key_file, timeout=15, allow_agent=False,
                            look_for_keys=not self.password)
                self._sftp = ssh.open_sftp()
            except Exception as exc:  # noqa: BLE001
                ssh.close()
                raise SourceError(f"SFTP connect failed: {exc}") from exc
            self._ssh = ssh
            return self._sftp

    def close(self) -> None:
        if self._ssh is not None:
            try:
                self._ssh.close()
            except Exception:  # noqa: BLE001
                pass
        self._ssh = self._sftp = None

    def _full(self, rel: str) -> str:
        return "/" + "/".join(p for p in (self.base, safe_rel(rel)) if p)

    def browse(self, dir_id: str = "") -> list[Entry]:
        rel = safe_rel(dec(dir_id)) if dir_id else ""
        sftp = self._client()
        out: list[Entry] = []
        try:
            for attr in sftp.listdir_attr(self._full(rel)):
                if attr.filename.startswith("."):
                    continue
                child = f"{rel}/{attr.filename}" if rel else attr.filename
                if stat.S_ISDIR(attr.st_mode or 0):
                    out.append(Entry(enc(child), attr.filename, "dir"))
                elif (kind := classify(attr.filename)):
                    out.append(Entry(enc(child), attr.filename, kind, size=attr.st_size))
        except OSError as exc:
            raise SourceError(f"SFTP browse failed: {exc}") from exc
        return sort_entries(out)

    def resolve(self, item_id: str) -> MediaRef:
        rel = safe_rel(dec(item_id))
        if not rel:
            raise SourceError("not a file")
        path = self._full(rel)
        sftp = self._client()
        try:
            size = sftp.stat(path).st_size
        except OSError as exc:
            raise SourceError(f"SFTP file not found: {exc}") from exc

        def opener():
            f = self._client().open(path, "rb")
            f.set_pipelined(True)
            return f

        name = posixpath.basename(path)
        return MediaRef(title=name.rsplit(".", 1)[0], kind=classify(name) or "video",
                        size=size, name=name, opener=opener)
