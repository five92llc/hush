"""Top bar panel data: scores, headlines, photo of the day and health."""
import httpx

from hush import ticker


def test_scores_put_live_games_first():
    def handler(req):
        ev = lambda st, a, b, d: {"date": d, "status": {"type": {"state": st, "shortDetail": "Q2 3:10" if st == "in" else st}},
                                  "competitions": [{"competitors": [{"homeAway": "home", "score": str(b), "team": {"abbreviation": "CHI"}},
                                                                    {"homeAway": "away", "score": str(a), "team": {"abbreviation": "NE"}}]}]}
        return httpx.Response(200, json={"events": [ev("pre", 0, 0, "2026-10-25T18:00Z"), ev("post", 24, 30, "2026-10-22T18:00Z"), ev("in", 7, 3, "2026-10-23T18:00Z")]})
    ticker._cache.clear()
    out = ticker.scores(["nfl", "bogus"], httpx.Client(transport=httpx.MockTransport(handler)))
    assert [g["state"] for g in out] == ["in", "post", "pre"] and out[0]["away"] == "NE" and out[0]["home_score"] == "3"


def test_headlines_from_rss_and_atom_and_bad_feeds():
    rss = b"<rss><channel><title>News</title><item><title>One</title></item><item><title>Two</title></item></channel></rss>"
    atom = b'<feed xmlns="http://www.w3.org/2005/Atom"><title>A</title><entry><title>Hello</title></entry></feed>'
    for body, first in ((rss, "One"), (atom, "Hello")):
        ticker._cache.clear()
        c = httpx.Client(transport=httpx.MockTransport(lambda r, b=body: httpx.Response(200, content=b)))
        assert ticker.headlines("https://x.test/feed", c)[0]["title"] == first
    ticker._cache.clear()
    assert ticker.headlines("ftp://x", None) == []
    assert ticker.headlines("https://x.test/bad", httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"<not xml")))) == []


def test_health_reports_disk(tmp_path):
    h = ticker.health(tmp_path)
    assert h["cpus"] >= 1 and h["disk_free_gb"] is not None
