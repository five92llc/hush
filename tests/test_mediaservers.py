"""Jellyfin, Plex and DLNA sources against canned API responses."""
import httpx
import pytest

from hush.sources.dlna import DLNASource
from hush.sources.mediaservers import JellyfinSource, PlexSource


class Resp:
    def __init__(self, url, json=None, text=""):
        self.url, self._json, self.text = url, json, text
        self.content = text.encode()
        self.status_code = 200

    def json(self):
        return self._json

    def raise_for_status(self):
        pass


def route(table):
    def fake(url, *a, **kw):
        for key, val in sorted(table.items(), key=lambda kv: -len(kv[0])):
            if url.endswith(key):
                return Resp(url, json=val if not isinstance(val, str) else None,
                            text=val if isinstance(val, str) else "")
        raise AssertionError(f"unexpected request {url}")
    return fake


def test_jellyfin(monkeypatch):
    monkeypatch.setattr(httpx, "get", route({
        "/Users": [{"Name": "family", "Id": "u1"}],
        "/Users/u1/Views": {"Items": [{"Id": "lib1", "Name": "Movies", "Type": "CollectionFolder", "IsFolder": True}]},
        "/Users/u1/Items/m1": {"Id": "m1", "Name": "Toy Story", "Type": "Movie",
                               "MediaSources": [{"Id": "ms1", "Path": "/media/Toy Story.mkv", "Size": 123}]},
        "/Users/u1/Items": {"Items": [{"Id": "m1", "Name": "Toy Story", "Type": "Movie", "ProductionYear": 1995},
                                      {"Id": "s1", "Name": "Bluey", "Type": "Series", "IsFolder": True}]},
    }))
    src = JellyfinSource({"id": "jf", "type": "jellyfin", "url": "http://jf:8096/", "api_key": "KEY"})
    assert [(e.name, e.kind) for e in src.browse()] == [("Movies", "dir")]
    assert [(e.name, e.kind) for e in src.browse("lib1")] == [("Toy Story", "video"), ("Bluey", "dir")]
    ref = src.resolve("m1")
    assert ref.url == "http://jf:8096/Videos/m1/stream?static=true&MediaSourceId=ms1"
    assert ref.headers["X-Emby-Token"] == "KEY" and ref.name == "Toy Story.mkv"


def test_plex(monkeypatch):
    monkeypatch.setattr(httpx, "get", route({
        "/library/sections/1/all": {"MediaContainer": {"Metadata": [
            {"ratingKey": "10", "title": "Up", "type": "movie", "year": 2009},
            {"ratingKey": "20", "title": "Bluey", "type": "show"}]}},
        "/library/sections": {"MediaContainer": {"Directory": [{"key": "1", "title": "Films", "type": "movie"},
                                                               {"key": "9", "title": "Photos", "type": "photo"}]}},
        "/library/metadata/10": {"MediaContainer": {"Metadata": [{"title": "Up", "type": "movie", "Media": [
            {"Part": [{"key": "/library/parts/5/file.mkv", "file": "D:\\Films\\Up.mkv", "size": 99}]}]}]}},
    }))
    src = PlexSource({"id": "px", "type": "plex", "url": "http://plex:32400", "token": "TOK"})
    assert [e.name for e in src.browse()] == ["Films"]          # photo libraries hidden
    assert [(e.name, e.kind) for e in src.browse("section:1")] == [("Up", "video"), ("Bluey", "dir")]
    ref = src.resolve("10")
    assert ref.url == "http://plex:32400/library/parts/5/file.mkv" and ref.name == "Up.mkv"
    assert ref.headers == {"X-Plex-Token": "TOK"}


DESC = """<?xml version="1.0"?><root xmlns="urn:schemas-upnp-org:device-1-0"><device>
<friendlyName>MiniDLNA</friendlyName><serviceList><service>
<serviceType>urn:schemas-upnp-org:service:ContentDirectory:1</serviceType>
<controlURL>/ctl/ContentDir</controlURL></service></serviceList></device></root>"""

DIDL_CHILDREN = """&lt;DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"&gt;
&lt;container id="64$1/2"&gt;&lt;dc:title&gt;Kids&lt;/dc:title&gt;&lt;/container&gt;
&lt;item id="64$3"&gt;&lt;dc:title&gt;Cars&lt;/dc:title&gt;&lt;upnp:class&gt;object.item.videoItem&lt;/upnp:class&gt;
&lt;res size="500" protocolInfo="http-get:*:video/x-matroska:*"&gt;http://nas:8200/MediaItems/3.mkv&lt;/res&gt;&lt;/item&gt;
&lt;/DIDL-Lite&gt;"""


def soap(result):
    return (f'<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
            f'<u:BrowseResponse xmlns:u="urn:schemas-upnp-org:service:ContentDirectory:1"><Result>{result}</Result>'
            f'</u:BrowseResponse></s:Body></s:Envelope>')


def test_dlna(monkeypatch):
    monkeypatch.setattr(httpx, "get", route({"rootDesc.xml": DESC}))
    seen = []

    def post(url, content=b"", **kw):
        seen.append(content.decode())
        assert url == "http://nas:8200/ctl/ContentDir"
        return Resp(url, text=soap(DIDL_CHILDREN))
    monkeypatch.setattr(httpx, "post", post)

    src = DLNASource({"id": "d", "type": "dlna", "location": "http://nas:8200/rootDesc.xml"})
    items = src.browse()
    assert [(e.name, e.kind) for e in items] == [("Kids", "dir"), ("Cars", "video")]
    assert "/" not in items[0].id                   # object ids with "/" are made URL-safe
    src.browse(items[0].id)
    assert "<ObjectID>64$1/2</ObjectID>" in seen[-1]
    ref = src.resolve(items[1].id)
    assert ref.url == "http://nas:8200/MediaItems/3.mkv" and ref.kind == "video"
