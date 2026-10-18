"""DLNA / UPnP AV media servers (MiniDLNA, Serviio, Universal Media Server,
Windows Media Player sharing, most NAS boxes).

Discovery uses SSDP multicast on the LAN; browsing uses the ContentDirectory
SOAP service. Resolved items are plain HTTP resources on the server.
"""
from __future__ import annotations

import socket
import time
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse

import httpx

from .base import Entry, MediaRef, Source, SourceError, classify, dec, enc, sort_entries

NS = {
    "d": "urn:schemas-upnp-org:device-1-0",
    "didl": "urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "upnp": "urn:schemas-upnp-org:metadata-1-0/upnp/",
}
CD_TYPE = "urn:schemas-upnp-org:service:ContentDirectory:1"


def discover(timeout: float = 2.5) -> list[dict]:
    """SSDP M-SEARCH for MediaServer devices. Returns [{name, location}]."""
    msg = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n"
           'MAN: "ssdp:discover"\r\nMX: 2\r\n'
           "ST: urn:schemas-upnp-org:device:MediaServer:1\r\n\r\n").encode()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    sock.settimeout(0.5)
    locations: set[str] = set()
    try:
        sock.sendto(msg, ("239.255.255.250", 1900))
        end = time.time() + timeout
        while time.time() < end:
            try:
                data, _ = sock.recvfrom(65507)
            except socket.timeout:
                continue
            for line in data.decode(errors="ignore").split("\r\n"):
                if line.lower().startswith("location:"):
                    locations.add(line.split(":", 1)[1].strip())
    except OSError:
        pass
    finally:
        sock.close()
    out = []
    for loc in sorted(locations):
        try:
            name, _ = _describe(loc)
            out.append({"name": name, "location": loc})
        except Exception:  # noqa: BLE001
            continue
    return out


def _describe(location: str) -> tuple[str, str]:
    """Return (friendlyName, ContentDirectory control URL) from a device description."""
    r = httpx.get(location, timeout=5)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    name = root.findtext(".//d:device/d:friendlyName", default="DLNA server", namespaces=NS)
    base = root.findtext("d:URLBase", default=location, namespaces=NS) or location
    for svc in root.iter(f"{{{NS['d']}}}service"):
        if (svc.findtext("d:serviceType", namespaces=NS) or "").startswith(CD_TYPE[:-1]):
            ctrl = svc.findtext("d:controlURL", namespaces=NS)
            return name, urljoin(base, ctrl)
    raise SourceError("device has no ContentDirectory service")


class DLNASource(Source):
    type = "dlna"

    def __init__(self, conf):
        super().__init__(conf)
        self.location = conf["location"]
        self._control: str | None = None

    def _ctrl(self) -> str:
        if not self._control:
            try:
                name, self._control = _describe(self.location)
            except Exception as exc:  # noqa: BLE001
                raise SourceError(f"DLNA server unreachable: {exc}") from exc
            if not self.conf.get("name"):
                self.name = name
        return self._control

    def _browse(self, object_id: str, flag: str) -> ET.Element:
        body = f"""<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
<s:Body><u:Browse xmlns:u="{CD_TYPE}">
<ObjectID>{_xml_escape(object_id)}</ObjectID><BrowseFlag>{flag}</BrowseFlag>
<Filter>*</Filter><StartingIndex>0</StartingIndex><RequestedCount>5000</RequestedCount>
<SortCriteria></SortCriteria></u:Browse></s:Body></s:Envelope>"""
        try:
            r = httpx.post(self._ctrl(), content=body.encode(), timeout=15, headers={
                "Content-Type": 'text/xml; charset="utf-8"',
                "SOAPAction": f'"{CD_TYPE}#Browse"'})
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise SourceError(f"DLNA browse failed: {exc}") from exc
        env = ET.fromstring(r.content)
        result = next((el.text for el in env.iter() if el.tag.endswith("Result")), None)
        if not result:
            raise SourceError("empty DLNA response")
        return ET.fromstring(result)

    def browse(self, dir_id: str = "") -> list[Entry]:
        # Object ids can contain "/" so they are wrapped for safe use in URLs.
        didl = self._browse(dec(dir_id) if dir_id else "0", "BrowseDirectChildren")
        out = []
        for c in didl.findall("didl:container", NS):
            out.append(Entry(enc(c.get("id")), c.findtext("dc:title", "", NS), "dir"))
        for it in didl.findall("didl:item", NS):
            res = it.find("didl:res", NS)
            if res is None:
                continue
            title = it.findtext("dc:title", "", NS)
            proto = res.get("protocolInfo", "")
            cls = it.findtext("upnp:class", "", NS)
            kind = "audio" if ("audio" in proto or ".audioItem" in cls) else (
                "video" if ("video" in proto or ".videoItem" in cls) else classify(res.text or ""))
            if kind:
                size = res.get("size")
                out.append(Entry(enc(it.get("id")), title, kind, size=int(size) if size else None))
        return sort_entries(out)

    def resolve(self, item_id: str) -> MediaRef:
        didl = self._browse(dec(item_id), "BrowseMetadata")
        it = didl.find("didl:item", NS)
        if it is None:
            raise SourceError("not a playable item")
        # Prefer the original (largest) resource over server transcodes.
        resources = it.findall("didl:res", NS)
        res = max(resources, key=lambda r: int(r.get("size") or 0))
        url = (res.text or "").strip()
        title = it.findtext("dc:title", "", NS)
        proto = res.get("protocolInfo", "")
        kind = "audio" if "audio" in proto else "video"
        name = urlparse(url).path.rsplit("/", 1)[-1]
        if "." not in name:
            mime = proto.split(":")[2] if proto.count(":") >= 2 else ""
            ext = {"video/x-matroska": ".mkv", "video/mp4": ".mp4", "audio/mpeg": ".mp3",
                   "audio/wav": ".wav", "audio/x-flac": ".flac", "video/x-msvideo": ".avi"}.get(mime, "")
            name = title + ext
        size = res.get("size")
        return MediaRef(title=title, kind=kind, url=url, name=name,
                        size=int(size) if size else None)


def _xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
