"""Turn timed words into mute ranges using a word list."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_WORDLIST = Path(__file__).parent / "wordlists" / "default.yaml"
SEVERITY = ["slurs", "strong", "sexual", "blasphemy", "mild"]  # first = most severe
_CENSORED = re.compile(r"^[a-z]{1,2}[*#@$%!]{1,}[a-z]{0,4}$")


@dataclass
class Word:
    text: str
    start: float
    end: float


def normalize(token: str) -> str:
    t = token.lower().replace("’", "'").replace("‘", "'")
    t = re.sub(r"^[^a-z0-9*]+|[^a-z0-9*]+$", "", t)
    t = t.replace("'", "").replace("-", "")
    return t


def _compile_token(p: str) -> tuple[str, str]:
    p = normalize(p) if "*" not in p else p.lower().replace("'", "").replace("-", "")
    if p.startswith("*") and p.endswith("*") and len(p) > 2:
        return "contains", p[1:-1]
    if p.endswith("*"):
        return "prefix", p[:-1]
    if p.startswith("*"):
        return "suffix", p[1:]
    return "exact", p


def _tok_match(pat: tuple[str, str], tok: str) -> bool:
    kind, s = pat
    if kind == "exact":
        return tok == s
    if kind == "prefix":
        return tok.startswith(s)
    if kind == "suffix":
        return tok.endswith(s)
    return s in tok


class WordList:
    def __init__(self, path: str | Path | None = None):
        data = yaml.safe_load(Path(path or DEFAULT_WORDLIST).read_text()) or {}
        self.categories: dict[str, dict] = {}
        self.patterns: list[tuple[str, list[tuple[str, str]]]] = []  # (category, token patterns)
        for cat, spec in (data.get("categories") or {}).items():
            self.categories[cat] = {"label": spec.get("label", cat), "default": spec.get("default", True)}
            for entry in spec.get("words") or []:
                toks = [t for t in str(entry).split() if t]
                if toks:
                    self.patterns.append((cat, [_compile_token(t) for t in toks]))
        # Longest phrases first so "son of a bitch" wins over "bitch".
        self.patterns.sort(key=lambda p: -len(p[1]))
        self.allow = [_compile_token(a) for a in data.get("allow") or []]

    def allowed(self, tok: str) -> bool:
        return any(_tok_match(a, tok) for a in self.allow)

    def categories_info(self) -> list[dict]:
        order = {c: i for i, c in enumerate(SEVERITY)}
        return [{"id": k, **v} for k, v in sorted(self.categories.items(),
                                                   key=lambda kv: order.get(kv[0], 99))]

    def find(self, words: list[Word]) -> list[dict]:
        """Return detections: {start, end, words, category, context}."""
        norm = [normalize(w.text) for w in words]
        out: list[dict] = []
        taken: set[int] = set()
        for i in range(len(words)):
            if not norm[i]:
                continue
            hit = None
            for cat, pats in self.patterns:
                n = len(pats)
                if i + n > len(words):
                    continue
                window = norm[i:i + n]
                if all(_tok_match(p, t) for p, t in zip(pats, window)):
                    if n == 1 and self.allowed(window[0]):
                        continue
                    hit = (cat, n)
                    break
            if hit is None and _CENSORED.match(norm[i]):
                hit = ("strong", 1)
            if hit is None:
                continue
            cat, n = hit
            idx = range(i, i + n)
            if all(j in taken for j in idx):
                continue
            taken.update(idx)
            ctx_words = [w.text.strip() for w in words[max(0, i - 6):i]]
            ctx_words += ["⟦" + " ".join(words[j].text.strip() for j in idx) + "⟧"]
            ctx_words += [w.text.strip() for w in words[i + n:i + n + 6]]
            out.append({
                "start": words[i].start, "end": words[i + n - 1].end,
                "words": [words[j].text.strip() for j in idx],
                "category": cat, "context": " ".join(ctx_words),
            })
        return out


def build_ranges(detections: list[dict], pad_before: float, pad_after: float,
                 merge_gap: float, duration: float | None = None) -> list[dict]:
    """Pad and merge detections into mute ranges."""
    order = {c: i for i, c in enumerate(SEVERITY)}
    items = sorted(detections, key=lambda d: d["start"])
    ranges: list[dict] = []
    for d in items:
        s = max(0.0, d["start"] - pad_before)
        e = d["end"] + pad_after
        if duration:
            e = min(e, duration)
        if e <= s:
            e = s + 0.25
        if ranges and s - ranges[-1]["end"] <= merge_gap and ranges[-1]["category"] == d["category"]:
            r = ranges[-1]
            r["end"] = max(r["end"], e)
            r["words"] += d["words"]
            r["context"] += " … " + d["context"]
            continue
        ranges.append({
            "id": uuid.uuid4().hex[:10], "start": round(s, 3), "end": round(e, 3),
            "words": list(d["words"]), "category": d["category"], "context": d["context"],
            "source": "auto", "enabled": True,
        })
    for r in ranges:
        r["start"], r["end"] = round(r["start"], 3), round(r["end"], 3)
    ranges.sort(key=lambda r: (r["start"], order.get(r["category"], 99)))
    return ranges


def carry_over(old: list[dict], new: list[dict]) -> list[dict]:
    """Keep manual ranges and the user's enable/disable choices across re-analysis."""
    manual = [r for r in old if r.get("source") == "manual"]
    disabled = [r for r in old if r.get("source") == "auto" and not r.get("enabled", True)]
    for r in new:
        for d in disabled:
            if r["start"] < d["end"] and d["start"] < r["end"]:
                r["enabled"] = False
                break
    return sorted(new + manual, key=lambda r: r["start"])
