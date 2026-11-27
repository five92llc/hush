"""Subtitle search and download, against a stand-in for OpenSubtitles."""
import httpx
import pytest

from hush import opensubtitles as os_


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_search_orders_by_popularity_and_sends_the_episode():
    def h(req):
        assert req.headers["api-key"] == "K" and req.url.params["season_number"] == "1" and req.url.params["episode_number"] == "3"
        item = lambda i, n: {"attributes": {"release": f"R{i}", "language": "en", "download_count": n, "files": [{"file_id": i}]}}
        return httpx.Response(200, json={"data": [item(1, 5), item(2, 50), {"attributes": {"files": []}}]})
    assert [r["file_id"] for r in os_.search("K", "Lupin", None, 1, 3, client=client(h))] == [2, 1]


def test_download_is_saved_beside_the_video_without_replacing(tmp_path):
    srt = b"1\n00:00:01,000 --> 00:00:02,000\nhi\n"

    def h(req):
        if req.url.path.endswith("/download"):
            return httpx.Response(200, json={"link": "https://files.test/a.srt"})
        return httpx.Response(200, content=srt)
    data = os_.fetch("K", 7, client=client(h))
    video = tmp_path / "Movie.mkv"; video.write_bytes(b"x")
    assert os_.save_beside(video, data, "en").name == "Movie.en.hush.srt" and os_.save_beside(video, data, "en").name == "Movie.en.hush2.srt"
    with pytest.raises(os_.SubtitleError, match="limit"):
        os_.fetch("K", 7, client=client(lambda r: httpx.Response(406, json={})))
