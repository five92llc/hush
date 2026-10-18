from hush.analysis.matcher import Word, WordList, build_ranges, carry_over, normalize
from hush.analysis.subtitles import cues_to_words, parse


def words(text, step=0.4):
    return [Word(w, i * step, i * step + step * 0.8) for i, w in enumerate(text.split())]


WL = WordList()


def cats(text):
    return [(d["category"], " ".join(d["words"])) for d in WL.find(words(text))]


def test_normalize():
    assert normalize("F*ck!") == "f*ck"
    assert normalize("God’s") == "gods"
    assert normalize("mother-fucker,") == "motherfucker"


def test_whole_words_only():
    assert cats("hello class assessment cockpit Dickens shell") == []
    assert cats("what the hell") == [("mild", "hell")]


def test_wildcards_and_phrases():
    assert cats("you motherfucker") == [("strong", "motherfucker")]
    assert cats("fucking idiot") == [("strong", "fucking")]
    assert cats("you son of a bitch") == [("strong", "son of a bitch")]
    assert cats("oh my god that's huge") == [("blasphemy", "oh my god")]


def test_prayer_is_not_blasphemy():
    assert cats("we thank God and Jesus for this day") == []


def test_self_censored_transcripts():
    assert cats("what the f***") == [("strong", "f***")]


def test_ranges_pad_and_merge():
    det = WL.find(words("shit shit shit okay"))
    rs = build_ranges(det, 0.1, 0.1, 0.35, duration=100)
    assert len(rs) == 1
    assert rs[0]["start"] == 0 and rs[0]["words"] == ["shit", "shit", "shit"]


def test_carry_over_keeps_user_choices():
    old = [{"id": "a", "start": 1.0, "end": 1.5, "source": "auto", "enabled": False},
           {"id": "m", "start": 9.0, "end": 9.5, "source": "manual", "enabled": True}]
    new = [{"id": "b", "start": 1.05, "end": 1.6, "source": "auto", "enabled": True}]
    out = carry_over(old, new)
    assert [r["id"] for r in out] == ["b", "m"]
    assert out[0]["enabled"] is False


def test_subtitle_parsing_and_timing():
    srt = "1\n00:00:01,000 --> 00:00:03,000\n<i>Hello</i> there\n\n2\n00:01:00.500 --> 00:01:02.000\n[MUSIC] damn it\n"
    cues = parse(srt)
    assert [c["text"] for c in cues] == ["Hello there", "[MUSIC] damn it"]
    ws = cues_to_words(cues)
    assert [w.text for w in ws] == ["Hello", "there", "damn", "it"]
    assert 1.0 <= ws[0].start < ws[1].start < 3.0
    ass = "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n" \
          "Dialogue: 0,0:00:05.00,0:00:07.00,Default,,0,0,0,,{\\i1}Oh hell{\\i0}, no\n"
    assert parse(ass) == [{"start": 5.0, "end": 7.0, "text": "Oh hell, no"}]
