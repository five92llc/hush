"""Viewer profiles: names only (no passwords), with a kids kind that only sees vetted titles.

A kids profile sees a title only when ALL of these hold:
  * the title has been scanned (unless the profile allows unscanned titles),
  * the scan found no more flagged moments than the profile allows, counting only the categories it blocks,
  * it has a content rating, and the rating is not above the profile's limit (a clean language scan says
    nothing about violence or explicit scenes, so an unrated title is hidden unless the profile allows it).
Everything else is hidden from lists and refused by the server if asked for directly.
"""
from __future__ import annotations

import json
import re

CATEGORIES = ("strong", "mild", "sexual", "slurs", "blasphemy")
COLORS = ("#A99CF0", "#F0B04A", "#6FC3A1", "#E2735F", "#6AA9E8", "#E08FB5", "#B5C96B", "#C79A6B")

# Pictures a profile can use. The drawings live in the web app, so they look the same on every screen
# (no dependence on an emoji font, which some TVs lack).
AVATARS = ("smile", "cool", "cat", "dog", "bear", "fox", "panda", "rabbit", "owl", "frog", "lion", "penguin",
           "robot", "alien", "dino", "ghost")

# Rating levels: 0 all ages, 1 PG, 2 teens, 3 mature, 4 adults only.
_CERTS = {"G": 0, "TV-Y": 0, "TV-G": 0, "PG": 1, "TV-Y7": 1, "TV-Y7-FV": 1, "TV-PG": 1, "PG-13": 2, "TV-14": 2,
          "R": 3, "TV-MA": 3, "NC-17": 4, "X": 4, "UNRATED": None, "NR": None}
_CERT_RE = re.compile(r"(NC-17|TV-Y7-FV|TV-Y7|TV-MA|TV-14|TV-PG|TV-G|TV-Y|PG-13|PG|G|R|X|UNRATED|NR)(?![A-Za-z0-9-])")
CERT_NAMES = {0: "G", 1: "PG", 2: "PG-13", 3: "R", 4: "NC-17"}

KIDS_DEFAULTS = {
    "block": list(CATEGORIES),   # word categories that make a title unsuitable
    "max_hits": 0,               # flagged moments allowed in those categories
    "max_cert": 1,               # highest rating level: 1 = PG
    "hide_unscanned": True,      # a title that was never scanned cannot be vouched for
    "allow_unrated": False,      # a title with no known rating cannot be vouched for either
    "allow_live": False,         # live TV cannot be scanned
}


def cert_level(text: str | None) -> int | None:
    """0-4 for a rating such as "Rated PG-13" or "US:TV-MA"; None when unknown or not recognised."""
    if not text:
        return None
    m = _CERT_RE.search(str(text).upper().replace("RATED", " ").replace("_", "-"))
    return _CERTS.get(m.group(1)) if m else None


def kid_settings(profile: dict | None) -> dict:
    return {**KIDS_DEFAULTS, **((profile or {}).get("settings") or {})}


def clean_settings(raw: dict) -> dict:
    """Only known keys, with sane types, from what the settings form sent."""
    out = {}
    if isinstance(raw.get("block"), list):
        out["block"] = [c for c in raw["block"] if c in CATEGORIES]
    if "max_hits" in raw:
        out["max_hits"] = max(0, min(50, int(raw["max_hits"])))
    if "max_cert" in raw:
        out["max_cert"] = max(0, min(5, int(raw["max_cert"])))          # 5 = no limit
    for k in ("hide_unscanned", "allow_unrated", "allow_live"):
        if k in raw:
            out[k] = bool(raw[k])
    return out


def approved(profile: dict | None, facts: dict | None) -> bool:
    """May this profile see this title? ``facts`` = {cert, show_cert, flags (JSON or dict), scanned}."""
    if not profile or not profile.get("kids"):
        return True
    if not facts:
        return False                              # not in the library: not vetted
    cfg = kid_settings(profile)
    if not facts.get("scanned"):
        if cfg["hide_unscanned"]:
            return False
    else:
        flags = facts.get("flags")
        flags = json.loads(flags) if isinstance(flags, str) and flags else (flags or {})
        hits = sum(n for cat, n in flags.items() if cat in cfg["block"] or cat == "manual")
        if hits > cfg["max_hits"]:
            return False
    level = cert_level(facts.get("cert"))
    if level is None:
        level = cert_level(facts.get("show_cert"))
    if level is None:
        return bool(cfg["allow_unrated"])
    return level <= cfg["max_cert"]


def public(profile: dict) -> dict:
    """What the picker and the app are told about a profile."""
    out = {"id": profile["id"], "name": profile["name"], "kids": bool(profile["kids"]), "color": profile.get("color") or COLORS[0],
           "avatar": profile.get("avatar") if profile.get("avatar") in AVATARS else ""}
    if out["kids"]:
        out["settings"] = kid_settings(profile)
    return out
