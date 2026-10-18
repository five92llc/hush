"""Work out what a movie or episode is from its file name (and NFO files)."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

# Words that mark the start of release-group clutter after the real title.
_JUNK = re.compile(
    r"(?<![A-Za-z0-9])(480p|576p|720p|1080[pi]|2160p|4k|uhd|web[ -]?dl|web[ -]?rip|webrip|web|hdrip|hdtv|"
    r"pdtv|bluray|blu-ray|brrip|bdrip|dvdrip|dcprip|dvdscr|remux|hevc|x26[45]|h[ .]?26[45]|avc|xvid|"
    r"10[ -]?bits?|hdr10?|hdr|dv|repack|proper|remastered|extended|unrated|internal|multi|dual|"
    r"aac|ac3|eac3|ddp?[ .]?\d|dd5|dts|atmos|truehd|hq|cam|hdts|line|amzn|nf|dsnp|hmax|atvp|pcok|hulu|"
    r"yts|yify|rarbg|eztv)(?![A-Za-z0-9])", re.I)
_EPISODE = re.compile(r"(?<![A-Za-z0-9])S(\d{1,2})[ ._-]?E(\d{1,3})(?:[ ._-]?E?(\d{1,3}))?(?![A-Za-z0-9])", re.I)
_EPISODE_X = re.compile(r"(?<![A-Za-z0-9])(\d{1,2})x(\d{2,3})(?![A-Za-z0-9])", re.I)
_SITE = re.compile(r"^\s*(www\.[\w.-]+|\[[^\]]*\])\s*[-–—]*\s*", re.I)
_YEAR_TAIL = re.compile(r"[\s(\[.-]*\b((?:19|20)\d{2})\b[\s)\].\-–—]*$")
_BAD_CHARS = re.compile(r'[<>"/\\|?*\x00-\x1f]')


def _spaced(name: str) -> str:
    """Dots and underscores are spaces in 'The.Movie.2020.1080p' style names."""
    if name.count(" ") >= name.count("."):
        return name
    return re.sub(r"[._]+", " ", name)


def _tidy(text: str) -> str:
    text = re.sub(r"(?<=\w)-\s+(?=[A-Z0-9])", ": ", text)        # "Spider-Man- Brand New Day"
    text = re.sub(r"\s+", " ", text).strip(" -–—_.,[]()")
    return text


def _cut_junk(text: str) -> str:
    cuts = [m.start() for m in (_JUNK.search(text),) if m]
    for ch in "[":
        i = text.find(ch)
        if i > 0:
            cuts.append(i)
    return text[:min(cuts)] if cuts else text


def parse_name(filename: str) -> dict:
    """{kind: movie|episode, title, year, season, episode, ep_title} from a file name."""
    stem = Path(filename).stem if re.search(r"\.\w{2,4}$", filename) else filename
    stem = _SITE.sub("", stem)
    text = _spaced(stem)

    m = _EPISODE.search(text) or _EPISODE_X.search(text)
    if m:
        show_part, after = text[:m.start()], text[m.end():]
        year = None
        ym = _YEAR_TAIL.search(_cut_junk(show_part))
        show_part = _cut_junk(show_part)
        if ym:
            year, show_part = int(ym.group(1)), show_part[:ym.start()]
        ep_title = _tidy(_cut_junk(re.sub(r"^[\s(\[-]*", "", re.sub(r"^\s*[-–—]\s*", "", after))))
        if _JUNK.fullmatch(ep_title or "x") or re.fullmatch(r"[\d ]*", ep_title):
            ep_title = ""
        return {"kind": "episode", "title": _tidy(show_part), "year": year,
                "season": int(m.group(1)), "episode": int(m.group(2)), "ep_title": ep_title}

    head = _cut_junk(text)
    year = None
    ym = _YEAR_TAIL.search(head)
    if ym and head[:ym.start()].strip(" -–—_.,[]()"):
        year, head = int(ym.group(1)), head[:ym.start()]
    return {"kind": "movie", "title": _tidy(head), "year": year, "season": None, "episode": None, "ep_title": ""}


def safe_name(text: str) -> str:
    """A name that is valid on Windows/SMB too: no reserved characters, no trailing dots."""
    text = text.replace(":", " -").replace("/", "-")
    return re.sub(r"\s+", " ", _BAD_CHARS.sub("", text)).strip(" .")


def display_title(meta: dict) -> str:
    return f"{meta['title']} ({meta['year']})" if meta.get("year") else meta["title"]


# ---- NFO (Kodi / Jellyfin / Plex sidecars) ---------------------------------------------
def read_nfo(path: Path) -> dict:
    """Fields from a .nfo file; {} when it is missing or not XML."""
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        text = re.sub(r"<\?xml[^>]*\?>", "", text)
        start = text.find("<")
        root = ET.fromstring(text[start:].strip())
    except (OSError, ET.ParseError, ValueError):
        return {}
    g = lambda tag: (root.findtext(tag) or "").strip()   # noqa: E731
    ids = {}
    for u in root.iter("uniqueid"):
        if u.get("type") and (u.text or "").strip():
            ids[u.get("type").lower()] = u.text.strip()
    for tag, name in (("imdbid", "imdb"), ("tmdbid", "tmdb"), ("tvdbid", "tvdb")):
        if g(tag):
            ids.setdefault(name, g(tag))
    year = g("year") or g("premiered")[:4] or g("releasedate")[:4]
    rating = root.findtext("rating") or (root.find("ratings/rating/value").text if root.find("ratings/rating/value") is not None else "")
    cert = g("mpaa") or g("contentrating") or g("certification")
    out = {"root": root.tag, "title": g("title"), "overview": g("plot"), "cert": cert,
           "year": int(year) if year.isdigit() else None,
           "genres": [e.text.strip() for e in root.findall("genre") if e.text],
           "runtime": int(g("runtime")) if g("runtime").isdigit() else None,
           "rating": float(rating) if re.fullmatch(r"\d+(\.\d+)?", (rating or "").strip()) else None,
           "ids": ids, "show": g("showtitle"),
           "season": int(g("season")) if g("season").lstrip("-").isdigit() else None,
           "episode": int(g("episode")) if g("episode").isdigit() else None}
    return {k: v for k, v in out.items() if v not in ("", None, [], {})}


def nfo_for(video: Path) -> dict:
    """The NFO that belongs to a video file: same name, or movie.nfo in its folder."""
    for cand in (video.with_suffix(".nfo"), video.parent / "movie.nfo"):
        if cand.is_file():
            return read_nfo(cand)
    return {}


def show_nfo_for(video: Path) -> dict:
    for folder in (video.parent, video.parent.parent):
        if (folder / "tvshow.nfo").is_file():
            return read_nfo(folder / "tvshow.nfo")
    return {}


POSTER_NAMES = ("poster", "folder", "cover", "movie", "thumb")
FANART_NAMES = ("fanart", "backdrop", "background", "art")
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp")
_SEASON_DIR = re.compile(r"^(season|series|staffel|saison|s)[ ._-]*\d{1,2}$|^specials?$", re.I)


def _find(folders, names) -> Path | None:
    """The first image among these folders with one of these names (any common picture extension)."""
    for folder in folders:
        for n in names:
            for ext in IMG_EXT:
                p = folder / f"{n}{ext}"
                if p.is_file():
                    return p
    return None


def show_folders(video: Path) -> list[Path]:
    """Folders that can hold a show's own artwork: the show folder, whether or not episodes sit in Season folders."""
    parent = video.parent
    return [parent.parent, parent] if _SEASON_DIR.match(parent.name) else [parent, parent.parent]


def local_fanart(video: Path) -> Path | None:
    """A background picture next to a movie (Kodi/Plex/Jellyfin naming: fanart.jpg, <name>-fanart.jpg, backdrop...)."""
    stem = video.stem
    return _find([video.parent], [f"{stem}-fanart", f"{stem}-backdrop", f"{stem}-background", *FANART_NAMES])


def local_episode_thumb(video: Path) -> Path | None:
    """An episode's own picture: <name>-thumb.jpg, <name>.jpg or <name>-landscape.jpg next to the video."""
    stem = video.stem
    return _find([video.parent], [f"{stem}-thumb", stem, f"{stem}-landscape"])


def local_show_poster(video: Path) -> Path | None:
    return _find(show_folders(video), ("poster", "folder", "cover", "show"))


def local_show_fanart(video: Path) -> Path | None:
    return _find(show_folders(video), FANART_NAMES)


def local_poster(video: Path) -> Path | None:
    """A poster image sitting next to the video (Kodi/Plex/Jellyfin naming)."""
    stem = video.stem
    names = [f"{stem}-poster", stem, *POSTER_NAMES]
    for n in names:
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            p = video.parent / f"{n}{ext}"
            if p.is_file():
                return p
    return None
