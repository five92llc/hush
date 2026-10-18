"""Find media servers on the local network by probing common ports.

Only the server's own /24 subnet is scanned, so this cannot be pointed at
other networks.
"""
from __future__ import annotations

import ipaddress
import socket
from concurrent.futures import ThreadPoolExecutor

# port -> (source type, label)
SERVICES = {
    445: ("smb", "SMB share"),
    21: ("ftp", "FTP"),
    22: ("sftp", "SFTP / SSH"),
    8096: ("jellyfin", "Jellyfin / Emby"),
    32400: ("plex", "Plex"),
}


def local_network() -> ipaddress.IPv4Network | None:
    """The /24 around this machine's LAN address, or None if it has no LAN."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))   # no packet is sent; picks the outgoing interface
        ip = ipaddress.ip_address(s.getsockname()[0])
    except OSError:
        return None
    finally:
        s.close()
    if not ip.is_private or ip.is_loopback:
        return None
    return ipaddress.ip_network(f"{ip}/24", strict=False)


def _open(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _name(host: str) -> str:
    try:
        return socket.gethostbyaddr(host)[0].split(".")[0]
    except OSError:
        return ""


def scan(timeout: float = 0.5) -> dict:
    net = local_network()
    if net is None:
        return {"network": None, "servers": []}
    hosts = [str(h) for h in net.hosts()]
    jobs = [(h, p) for h in hosts for p in SERVICES]
    with ThreadPoolExecutor(max_workers=96) as pool:
        results = list(pool.map(lambda hp: _open(hp[0], hp[1], timeout), jobs))
    found: dict[str, list[dict]] = {}
    for (host, port), ok in zip(jobs, results):
        if ok:
            kind, label = SERVICES[port]
            found.setdefault(host, []).append({"type": kind, "port": port, "label": label})
    with ThreadPoolExecutor(max_workers=16) as pool:
        names = dict(zip(found, pool.map(_name, found)))
    servers = [{"host": h, "name": names[h], "services": svc}
               for h, svc in sorted(found.items(), key=lambda kv: ipaddress.ip_address(kv[0]))]
    return {"network": str(net), "servers": servers}
