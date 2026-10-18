"""Local folders, including NAS shares already mounted on the host (NFS/CIFS)."""
from __future__ import annotations

import os
from pathlib import Path

from .base import Entry, MediaRef, Source, SourceError, SUB_EXT, classify, dec, enc, sort_entries


class LocalSource(Source):
    type = "local"

    def __init__(self, conf):
        super().__init__(conf)
        paths = conf.get("paths") or ([conf["path"]] if conf.get("path") else [])
        if not paths:
            raise SourceError(f"local source {self.id}: no 'path' or 'paths'")
        self.roots = [Path(p).expanduser().resolve() for p in paths]

    # ids look like "<root index>:<relative posix path>"
    def _to_path(self, item_id: str) -> Path:
        if not item_id:
            raise SourceError("empty id")
        idx_s, _, rel = dec(item_id).partition(":")
        try:
            root = self.roots[int(idx_s)]
        except (ValueError, IndexError):
            raise SourceError("bad id")
        target = (root / rel).resolve()
        # Path traversal guard: the resolved path must stay inside its root.
        if target != root and root not in target.parents:
            raise SourceError("path outside source root")
        return target

    def _to_id(self, idx: int, path: Path) -> str:
        rel = path.relative_to(self.roots[idx]).as_posix()
        return enc(f"{idx}:{'' if rel == '.' else rel}")

    def browse(self, dir_id: str = "") -> list[Entry]:
        if not dir_id:
            if len(self.roots) > 1:
                return [Entry(self._to_id(i, r), r.name or str(r), "dir")
                        for i, r in enumerate(self.roots)]
            dir_id = self._to_id(0, self.roots[0])
        idx = int(dec(dir_id).partition(":")[0])
        folder = self._to_path(dir_id)
        if not folder.is_dir():
            raise SourceError("not a folder")
        out: list[Entry] = []
        try:
            with os.scandir(folder) as it:
                for de in it:
                    if de.name.startswith("."):
                        continue
                    p = Path(de.path)
                    try:
                        if de.is_dir():
                            out.append(Entry(self._to_id(idx, p), de.name, "dir"))
                            continue
                        kind = classify(de.name)
                        if kind:
                            out.append(Entry(self._to_id(idx, p), de.name, kind,
                                             size=de.stat().st_size))
                    except (OSError, ValueError):
                        continue
        except PermissionError:
            raise SourceError("permission denied")
        return sort_entries(out)

    def resolve(self, item_id: str) -> MediaRef:
        path = self._to_path(item_id)
        if not path.is_file():
            raise SourceError("file not found")
        kind = classify(path.name) or "video"
        subs = [str(s) for s in sorted(path.parent.glob(path.stem + "*"))
                if s.suffix.lower() in SUB_EXT]
        return MediaRef(title=path.stem, kind=kind, path=str(path),
                        size=path.stat().st_size, name=path.name, subtitle_paths=subs)
