"""Find and fetch subtitles for a title that has none, from OpenSubtitles (needs your own free API key from opensubtitles.com)."""
from __future__ import annotations

import re
from pathlib import Path

import httpx

API = "https://api.opensubtitles.com/api/v1"
AGENT = "Hush v1.0"


class SubtitleError(Exception):
    pass


def _headers(key: str, token: str = "") -> dict:
    h = {"Api-Key": key, "User-Agent": AGENT, "Accept": "application/json", "Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _ask(client, method: str, url: str, **kw) -> dict:
    try:
        r = (client or httpx).request(method, url, timeout=20, follow_redirects=True, **kw)
    except httpx.HTTPError as exc:
        raise SubtitleError(f"Could not reach OpenSubtitles: {exc}")
    if r.status_code in (401, 403):
        raise SubtitleError("OpenSubtitles refused the key or sign-in. Check them in Settings.")
    if r.status_code in (406, 429):
        raise SubtitleError("OpenSubtitles says today's download limit is reached. Try again tomorrow.")
    if r.status_code >= 400:
        raise SubtitleError(f"OpenSubtitles answered with error {r.status_code}")
    try:
        return r.json()
    except ValueError:
        raise SubtitleError("OpenSubtitles sent something unreadable")


def search(key: str, title: str, year: int | None = None, season: int | None = None, episode: int | None = None, language: str = "en", client=None) -> list[dict]:
    params = {"query": title, "languages": language}
    if season is not None and episode is not None:
        params |= {"season_number": season, "episode_number": episode}
    elif year:
        params["year"] = year
    data = _ask(client, "GET", f"{API}/subtitles", params=params, headers=_headers(key)).get("data") or []
    out = []
    for d in data:
        a = d.get("attributes") or {}
        files = a.get("files") or []
        if files and files[0].get("file_id"):
            out.append({"file_id": int(files[0]["file_id"]), "name": str(a.get("release") or files[0].get("file_name") or "Subtitles")[:160],
                        "language": a.get("language") or language, "downloads": int(a.get("download_count") or 0), "hearing": bool(a.get("hearing_impaired"))})
    return sorted(out, key=lambda x: -x["downloads"])[:15]


def fetch(key: str, file_id: int, username: str = "", password: str = "", client=None) -> bytes:
    token = ""
    if username and password:
        token = _ask(client, "POST", f"{API}/login", json={"username": username, "password": password}, headers=_headers(key)).get("token", "")
    link = _ask(client, "POST", f"{API}/download", json={"file_id": int(file_id), "sub_format": "srt"}, headers=_headers(key, token)).get("link", "")
    if not link.startswith("https://"):
        raise SubtitleError("OpenSubtitles gave no download link")
    try:
        r = (client or httpx).request("GET", link, timeout=30, follow_redirects=True, headers={"User-Agent": AGENT})
        r.raise_for_status()
    except httpx.HTTPError as exc:
        raise SubtitleError(f"The subtitle file could not be fetched: {exc}")
    if len(r.content) > 5_000_000 or b"-->" not in r.content:
        raise SubtitleError("That file is not a subtitle file")
    return r.content


def save_beside(video: Path, data: bytes, language: str) -> Path:
    """Put the file next to the video, where Hush (and other players) already look. Never replaces a file."""
    lang = re.sub(r"[^a-z-]", "", language.lower())[:8] or "en"
    for n in range(1, 20):
        out = video.with_name(f"{video.stem}.{lang}.hush{'' if n == 1 else n}.srt")
        try:
            with open(out, "xb") as f:
                f.write(data)
            return out
        except FileExistsError:
            continue
        except OSError as exc:
            raise SubtitleError(f"Hush may not write in that folder: {exc.strerror}")
    raise SubtitleError("There are already many subtitle files for this video")
