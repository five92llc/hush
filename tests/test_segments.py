"""Intros and credits: chapters, the fingerprint comparison, and the marks stored for the player."""
import subprocess

import pytest

np = pytest.importorskip("numpy")

from hush import segments
from hush.db import DB


def test_chapters_name_the_intro_and_the_credits():
    ch = [{"start_time": "0", "end_time": "50", "tags": {"title": "Cold open"}}, {"start_time": "50", "end_time": "140", "tags": {"title": "Opening"}},
          {"start_time": "140", "end_time": "2500", "tags": {"title": "Chapter 3"}}, {"start_time": "2600", "end_time": "2700", "tags": {"title": "End Credits"}}]
    out = segments.chapter_segments(ch, 2700.0)
    assert out["intro"] == (50.0, 140.0) and out["credits"] == (2600.0, 2700.0)


def test_best_alignment_finds_the_shared_stretch():
    rng = np.random.default_rng(1)
    theme = rng.integers(0, 2 ** 32, 400, dtype=np.uint64).astype(np.uint32)            # ~50 s of "tune"
    a = np.concatenate([rng.integers(0, 2 ** 32, 120, dtype=np.uint64).astype(np.uint32), theme, rng.integers(0, 2 ** 32, 300, dtype=np.uint64).astype(np.uint32)])
    b = np.concatenate([rng.integers(0, 2 ** 32, 330, dtype=np.uint64).astype(np.uint32), theme, rng.integers(0, 2 ** 32, 100, dtype=np.uint64).astype(np.uint32)])
    ia, ib, n = segments.best_alignment(a, b, max_shift=600, min_items=100)
    assert abs(ia - 120) <= 2 and abs(ib - 330) <= 2 and abs(n - 400) <= 6
    c = rng.integers(0, 2 ** 32, 900, dtype=np.uint64).astype(np.uint32)
    assert segments.best_alignment(a, c, max_shift=600, min_items=100) is None           # nothing in common


def tune(path, seconds, offset_theme, other):
    """A file whose sound is `other` music with the same 30 s theme starting at `offset_theme`."""
    theme = "+".join(f"0.3*sin(2*PI*{f}*t)*between(mod(t,3),{i},{i + 1})" for i, f in enumerate((440, 660, 880)))
    noise = f"0.3*sin(2*PI*{other}*t*(1+0.3*sin(t)))"
    expr = f"if(between(t,{offset_theme},{offset_theme + 30}),{theme},{noise})"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"aevalsrc={expr.replace(',', chr(92) + ',')}:s=11025:d={seconds}", str(path)], check=True)


def fingerprint(path):
    raw = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path), "-ac", "1", "-ar", "11025", "-f", "chromaprint", "-fp_format", "raw", "pipe:1"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype="<u4").copy()


def has_chromaprint() -> bool:
    out = subprocess.run(["ffmpeg", "-hide_banner", "-muxers"], capture_output=True, text=True).stdout
    return "chromaprint" in out


@pytest.mark.skipif(not has_chromaprint(), reason="this ffmpeg has no chromaprint")
def test_a_theme_shared_by_two_files_is_found_by_its_sound(tmp_path):
    tune(tmp_path / "a.wav", 120, 10, 300)
    tune(tmp_path / "b.wav", 120, 35, 520)
    fa, fb = fingerprint(tmp_path / "a.wav"), fingerprint(tmp_path / "b.wav")
    m = segments.best_alignment(fa, fb, max_shift=1000, min_items=int(15 / segments.ITEM))
    assert m, "the theme was not found"
    ia, ib, n = m
    assert abs(ia * segments.ITEM - 10) < 3 and abs(ib * segments.ITEM - 35) < 3 and abs(n * segments.ITEM - 30) < 4


def test_marks_are_stored_and_manual_ones_win(tmp_path):
    db = DB(tmp_path / "h.db")
    db.set_segment("k", "intro", 10, 60, "detected")
    db.set_segment("k", "intro", 12, 58, "manual")
    assert db.get_segments("k") == [{"kind": "intro", "start": 12.0, "end": 58.0, "source": "manual"}]
    db.delete_segment("k", "intro")
    assert db.get_segments("k") == []
    db.set_segment_scan("show:1", 8)
    assert db.get_segment_scan("show:1")["episodes"] == 8
