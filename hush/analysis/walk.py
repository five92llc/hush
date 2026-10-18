"""Walk a source's folders and yield every playable title."""
from __future__ import annotations

import logging
import re
from typing import Iterator

from ..sources.base import Entry, Source

log = logging.getLogger("hush.walk")
_EXTRA = re.compile(r"\b(sample|trailer|featurette)\b", re.I)   # not worth scanning


def walk(src: Source, errors: list[str] | None = None, dir_id: str = "",
         max_depth: int = 8, limit: int = 20000) -> Iterator[Entry]:
    """Breadth-first over folders. Live streams, samples and trailers are left out.
    Folders that cannot be opened are noted in ``errors`` and skipped."""
    todo = [(dir_id, 0)]
    seen = 0
    while todo and seen < limit:
        folder, depth = todo.pop(0)
        try:
            entries = src.browse(folder)
        except Exception as exc:  # noqa: BLE001
            log.warning("cannot open %s in %s: %s", folder or "/", src.id, exc)
            if errors is not None:
                errors.append(f"{src.id}: {exc}")
            continue
        for e in entries:
            if e.kind != "dir" and not e.meta.get("live") and not _EXTRA.search(e.name):
                seen += 1
                yield e
        if depth < max_depth:
            todo += [(e.id, depth + 1) for e in entries if e.kind == "dir"]
