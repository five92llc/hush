"""Tidy file names: plan, apply and undo.

Layouts:
  flat     every file directly in the source folder (the default)
             Movies   Title (Year).ext
             Shows    Show (Year) - S01E02 - Episode Title.ext
  folders  the layout Plex, Jellyfin and Kodi like
             Movies   Title (Year)/Title (Year).ext
             Shows    Show (Year)/Season 01/Show (Year) - S01E02 - Episode Title.ext

Safety rules: only Local sources; nothing is changed until you apply a previewed
plan; nothing is ever overwritten; every step is journaled so a batch can be undone.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path

from ..sources.base import classify, dec
from .parse import display_title, parse_name, safe_name
from .providers import norm

SIDE_SEPARATORS = ".-_ "
LAYOUTS = ("flat", "folders")
GENERIC_IMAGES = {"poster", "folder", "cover", "movie", "thumb"}


class RenameError(Exception):
    pass


def _is_video(p: Path) -> bool:
    return p.is_file() and classify(p.name) is not None


def _season_dir(season: int) -> str:
    return "Specials" if season == 0 else f"Season {season:02d}"


def _sidecars(video: Path) -> list[Path]:
    stem = video.stem
    out = []
    for f in sorted(video.parent.iterdir()):
        if (f.is_file() and f != video and classify(f.name) is None and f.name.startswith(stem)
                and len(f.name) > len(stem) and f.name[len(stem)] in SIDE_SEPARATORS):
            out.append(f)
    return out


class Renamer:
    def __init__(self, db, registry):
        self.db, self.registry = db, registry

    # ---- planning ---------------------------------------------------------------
    def _local(self, source_id: str):
        src = self.registry.get(source_id)
        if src.type != "local":
            raise RenameError("Tidying names only works on folders on the server (Local sources)")
        return src

    def _entries(self, src, only_matched: bool):
        entries, skipped = [], []
        for m in self.db._all("SELECT * FROM meta WHERE source_id=? ORDER BY item_id", (src.id,)):
            m = self.db._decode(m)
            try:
                path = src._to_path(m["item_id"])
                idx = int(dec(m["item_id"]).partition(":")[0])
            except Exception:  # noqa: BLE001
                continue
            if not path.is_file():
                continue
            if only_matched and m["provider"] == "name":
                skipped.append({"name": path.name, "reason": "no match found online; fix the match first or include unmatched titles"})
                continue
            if not m.get("title") and m["kind"] == "movie":
                continue
            entries.append({"meta": m, "path": path, "root": src.roots[idx], "idx": idx})
        return entries, skipped

    def _names(self, e: dict) -> tuple[str, Path, str] | None:
        """(new file stem, destination folder, label) for one title (folder layout)."""
        m, root = e["meta"], e["root"]
        if m["kind"] == "movie":
            base = safe_name(display_title(m))
            return (base, root / base, base) if base else None
        show = self.db.get_show(m["show_key"]) if m.get("show_key") else None
        if not show or m.get("season") is None or m.get("episode") is None:
            return None
        show_dir = safe_name(display_title(show))
        stem = f"{show_dir} - S{m['season']:02d}E{m['episode']:02d}"
        if m.get("title"):
            stem += f" - {safe_name(m['title'])}"
        return stem, root / show_dir / _season_dir(m["season"]), show_dir

    def plan(self, source_id: str, only_matched: bool = True, layout: str = "flat") -> dict:
        if layout not in LAYOUTS:
            raise RenameError("Unknown layout")
        src = self._local(source_id)
        entries, skipped = self._entries(src, only_matched)
        by_dir: dict[Path, list[dict]] = {}
        for e in entries:
            by_dir.setdefault(e["path"].parent, []).append(e)

        groups: list[dict] = []
        tidy = 0
        for folder, items in sorted(by_dir.items(), key=lambda kv: str(kv[0])):
            videos = [f for f in folder.iterdir() if _is_video(f)]
            root = items[0]["root"]
            named = []
            for e in items:
                n = self._names(e)
                if n is None:
                    skipped.append({"name": e["path"].name, "reason": "missing season or episode number"})
                else:
                    named.append((e, n))
            if not named:
                continue
            if layout == "flat":
                found = self._plan_flat(folder, root, videos, named)
            else:
                found = [self._plan_movie(folder, root, videos, e, n) for e, n in named if e["meta"]["kind"] == "movie"]
                eps = [(e, n) for e, n in named if e["meta"]["kind"] == "episode"]
                if eps:
                    found += self._plan_episodes(folder, root, videos, eps)
            tidy += len(named) - sum(len(g["items"]) for g in found if g)
            groups += [g for g in found if g]

        groups = self._drop_conflicts(groups, skipped)
        for g in groups:
            g["id"] = hashlib.sha1(json.dumps(g["ops"]).encode()).hexdigest()[:12]
        return {"groups": groups, "skipped": skipped, "tidy": tidy, "root_names": [str(r) for r in src.roots]}

    def _group(self, label: str, kind: str, items: list[dict], ops: list[list[str]]) -> dict:
        return {"label": label, "kind": kind, "items": items, "ops": ops}

    def _plan_movie(self, folder: Path, root: Path, videos: list[Path], e: dict, n: tuple):
        stem, dest_dir, label = n
        old = e["path"]
        release_folder = (folder != root and len(videos) == 1 and
                          norm(parse_name(folder.name)["title"]) == norm(parse_name(old.name)["title"]))
        ops: list[list[str]] = []
        if release_folder:
            new_dir = folder.parent / label
            if new_dir != folder:
                ops.append(["move", str(folder), str(new_dir)])
            file_ops, new_video = self._file_ops_after_dir_move(old, new_dir, stem)   # sidecars are read before the move
            ops += file_ops
        else:
            ops.append(["mkdir", str(dest_dir)])
            ops += [["move", str(f), str(dest_dir / (stem + f.name[len(old.stem):]))] for f in [old, *_sidecars(old)]]
            new_video = dest_dir / f"{stem}{old.suffix}"
            if folder != root and not [f for f in folder.iterdir() if f not in [old, *_sidecars(old)]]:
                ops.append(["rmdir", str(folder)])
        if old == new_video:
            return None
        return self._group(label, "movie", [{"key": e["meta"]["media_key"], "from": str(old), "to": str(new_video)}], ops)

    def _plan_flat(self, folder: Path, root: Path, videos: list[Path], named: list) -> list[dict]:
        """Everything goes straight into the source folder; emptied folders are removed."""
        loose = folder == root
        buckets = [[x] for x in named] if loose else [named]        # loose files: one group per title
        out = []
        for bucket in buckets:
            ops, items = [], []
            for e, (stem, _, label) in bucket:
                old = e["path"]
                single = not loose and len(videos) == 1
                moving = [(f, stem + f.name[len(old.stem):]) for f in [old, *_sidecars(old)]]
                if single and e["meta"]["kind"] == "movie":          # movie.nfo / poster.jpg belong to this movie
                    for f in sorted(folder.iterdir()):
                        if not f.is_file() or f == old or any(f == m[0] for m in moving) or classify(f.name):
                            continue
                        if f.stem.lower() == "movie" and f.suffix.lower() == ".nfo":
                            moving.append((f, f"{stem}.nfo"))
                        elif f.stem.lower() in GENERIC_IMAGES and f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                            moving.append((f, f"{stem}-poster{f.suffix.lower()}"))
                for f, new_name in moving:
                    if f.parent != root or f.name != new_name:
                        ops.append(["move", str(f), str(root / new_name)])
                to = root / f"{stem}{old.suffix}"
                if str(to) != str(old):
                    items.append({"key": e["meta"]["media_key"], "from": str(old), "to": str(to)})
            if not items:
                continue
            up = folder
            while up != root and root in up.parents:                 # emptied folders go; ones with leftovers stay
                ops.append(["rmdir", str(up)])
                up = up.parent
            label = bucket[0][1][2] if loose else f"{bucket[0][1][2]} · {len(items)} file{'s' if len(items) != 1 else ''}"
            if not loose and len({e["meta"]["kind"] for e, _ in bucket}) == 1 and bucket[0][0]["meta"]["kind"] == "episode":
                label = f"{bucket[0][1][2]} · {len(items)} episode{'s' if len(items) != 1 else ''}"
            out.append(self._group(label, "flat", items, ops))
        return out

    def _file_ops_after_dir_move(self, old: Path, new_dir: Path, stem: str):
        ops = []
        for f in [old, *_sidecars(old)]:
            current = new_dir / f.name
            target = new_dir / (stem + f.name[len(old.stem):])
            if current != target:
                ops.append(["move", str(current), str(target)])
        return ops, new_dir / f"{stem}{old.suffix}"

    def _plan_files(self, folder: Path, root: Path, named: list, only_if_last: bool = False):
        ops, items, label = [], [], ""
        for e, (stem, dest_dir, label) in named:
            old = e["path"]
            ops.append(["mkdir", str(dest_dir)])
            moving = [old, *_sidecars(old)]
            ops += [["move", str(f), str(dest_dir / (stem + f.name[len(old.stem):]))] for f in moving]
            items.append({"key": e["meta"]["media_key"], "from": str(old), "to": str(dest_dir / f"{stem}{old.suffix}")})
        items = [i for i in items if i["from"] != i["to"]]
        if not items:
            return None
        if folder != root and only_if_last:        # the folder is only removed when everything in it moved
            ops.append(["rmdir", str(folder)])
        return self._group(label, "files", items, ops)

    def _plan_episodes(self, folder: Path, root: Path, videos: list[Path], named: list) -> list[dict]:
        parts: dict[tuple, list] = {}
        for e, n in named:
            parts.setdefault((e["meta"]["show_key"], e["meta"]["season"]), []).append((e, n))
        whole_folder = folder != root and len(parts) == 1 and len(videos) == len(named)
        stem0, dest_dir, label = named[0][1]
        if whole_folder and not dest_dir.exists() and folder != dest_dir:
            ops = [["mkdir", str(dest_dir.parent)], ["move", str(folder), str(dest_dir)]]
            items = []
            for e, (stem, _, _) in named:
                old = e["path"]
                file_ops, new_video = self._file_ops_after_dir_move(old, dest_dir, stem)
                ops += file_ops
                items.append({"key": e["meta"]["media_key"], "from": str(old), "to": str(new_video)})
            parent = folder.parent
            if parent != root and parent != dest_dir.parent:
                ops.append(["rmdir", str(parent)])
            return [self._group(f"{label} · {dest_dir.name}", "folder", items, ops)]
        out = []
        for (_, season), group in parts.items():
            g = self._plan_files(folder, root, group, only_if_last=len(parts) == 1 and len(videos) == len(group))
            if g:
                g["label"] = f"{group[0][1][2]} · {_season_dir(season)} · {len(g['items'])} episode{'s' if len(g['items']) != 1 else ''}"
                out.append(g)
        return out

    def _drop_conflicts(self, groups: list[dict], skipped: list[dict]) -> list[dict]:
        """Refuse any group whose files would land on an existing path or on another group's."""
        claimed: dict[str, int] = {}
        for i, g in enumerate(groups):
            for it in g["items"]:
                claimed.setdefault(it["to"], 0)
                claimed[it["to"]] += 1
        ok = []
        for g in groups:
            reason = None
            for it in g["items"]:
                to = Path(it["to"])
                if claimed[it["to"]] > 1:
                    reason = "two files would get the same name"
                elif to.exists() and to != Path(it["from"]):
                    reason = "a file with the new name already exists"
            for op in g["ops"]:
                if op[0] == "move" and op[1] != op[2]:
                    dst = Path(op[2])
                    if dst.exists() and not any(op[2] == o[1] for o in g["ops"] if o[0] == "move"):
                        reason = reason or f"{dst.name} already exists"
            if reason:
                skipped.append({"name": g["label"], "reason": reason})
            else:
                ok.append(g)
        return ok

    # ---- applying -----------------------------------------------------------------
    def apply(self, source_id: str, ids: list[str], only_matched: bool = True, layout: str = "flat") -> dict:
        src = self._local(source_id)
        plan = self.plan(source_id, only_matched, layout)
        wanted = [g for g in plan["groups"] if g["id"] in set(ids)]
        if not wanted:
            raise RenameError("Nothing to rename: the folders changed since the preview. Preview again.")
        batch = uuid.uuid4().hex[:10]
        done, failed = 0, []
        for g in wanted:
            try:
                self._run_group(src, batch, g)
                done += len(g["items"])
            except (OSError, RenameError) as exc:
                failed.append({"name": g["label"], "reason": str(exc)})
        return {"batch": batch, "renamed": done, "failed": failed}

    def _run_group(self, src, batch: str, g: dict) -> None:
        for op in g["ops"]:                                    # permission check before touching anything
            if op[0] == "rmdir":
                continue
            anchor = Path(op[1]).parent if op[0] == "move" else Path(op[1])
            while not anchor.exists():
                anchor = anchor.parent
            if not os.access(anchor, os.W_OK):
                raise RenameError("Hush has no permission to change this folder (is it mounted read-only?)")
        executed: list[list[str]] = []
        rows: list[int] = []
        try:
            for op in g["ops"]:
                kind = op[0]
                if kind == "mkdir":
                    if not Path(op[1]).exists():
                        Path(op[1]).mkdir(parents=True)
                        executed.append(op)
                        rows.append(self.db.journal(batch, src.id, "mkdir", op[1], ""))
                elif kind == "move":
                    s, d = Path(op[1]), Path(op[2])
                    if not s.exists():
                        raise RenameError(f"{s.name} is no longer there")
                    if d.exists():
                        raise RenameError(f"{d.name} already exists")
                    d.parent.mkdir(parents=True, exist_ok=True)
                    os.rename(s, d)
                    executed.append(op)
                    rows.append(self.db.journal(batch, src.id, "move", op[1], op[2]))
                elif kind == "rmdir":
                    p = Path(op[1])
                    if p.is_dir() and not any(p.iterdir()):
                        p.rmdir()
                        executed.append(op)
                        rows.append(self.db.journal(batch, src.id, "rmdir", op[1], ""))
        except (OSError, RenameError):
            self._reverse(executed)
            self.db.drop_journal(rows)
            raise
        self._rekey(src, batch, g)

    def _reverse(self, executed: list[list[str]]) -> None:
        for op in reversed(executed):
            try:
                if op[0] == "move":
                    os.rename(op[2], op[1])
                elif op[0] == "mkdir":
                    Path(op[1]).rmdir()
                elif op[0] == "rmdir":
                    Path(op[1]).mkdir(parents=True, exist_ok=True)
            except OSError:
                pass

    def _rekey(self, src, batch: str, g: dict) -> None:
        for it in g["items"]:
            new_path = Path(it["to"])
            idx = next(i for i, r in enumerate(src.roots) if r == new_path or r in new_path.parents)
            new_id = src._to_id(idx, new_path)
            new_key = self._key(src.id, new_id)
            old = self.db._one("SELECT item_id FROM meta WHERE media_key=?", (it["key"],))
            self.db.rekey(it["key"], new_key, src.id, new_id)
            self.db.journal(batch, src.id, "rekey", f"{it['key']}|{old['item_id'] if old else ''}", f"{new_key}|{new_id}")
            self._move_cache(it["key"], new_key)

    def _key(self, source_id: str, item_id: str) -> str:
        from ..sources import media_key
        return media_key(source_id, item_id)

    cache_dir: Path | None = None
    art_dir: Path | None = None

    def _move_cache(self, old: str, new: str) -> None:
        for base, suffix in ((self.cache_dir, ".words.json"), (self.art_dir, ".jpg")):
            if base and (base / f"{old}{suffix}").exists():
                (base / f"{old}{suffix}").replace(base / f"{new}{suffix}")

    # ---- undo ---------------------------------------------------------------------------
    def undo(self, batch: str) -> dict:
        steps = self.db.rename_steps(batch)
        if not steps or all(s["undone"] for s in steps):
            raise RenameError("That batch was already undone")
        problems = []
        for s in reversed(steps):
            try:
                if s["kind"] == "move":
                    if Path(s["src"]).exists():
                        raise RenameError(f"{Path(s['src']).name} exists again, so it was left alone")
                    os.rename(s["dst"], s["src"])
                elif s["kind"] == "mkdir":
                    p = Path(s["src"])
                    if p.is_dir() and not any(p.iterdir()):
                        p.rmdir()
                elif s["kind"] == "rmdir":
                    Path(s["src"]).mkdir(parents=True, exist_ok=True)
                elif s["kind"] == "rekey":
                    new_key, new_id = s["dst"].split("|", 1)
                    old_key, old_id = s["src"].split("|", 1)
                    self.db.rekey(new_key, old_key, s["source_id"], old_id)
                    self._move_cache(new_key, old_key)
            except (OSError, RenameError) as exc:
                problems.append(str(exc))
        self.db.mark_undone(batch)
        return {"undone": True, "problems": problems}
