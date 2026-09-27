"""Client IP. Trust a proxy header only when the peer is a private proxy."""

import ipaddress

from app.config import Settings


def client_ip(request, settings: Settings) -> str:
    peer = ""
    if request.client and request.client.host:
        peer = request.client.host
    header = (settings.trusted_proxy_header or "").strip()
    if header and _is_proxy(peer):
        raw = request.headers.get(header, "")
        if header.lower() == "x-forwarded-for":
            raw = raw.split(",")[0].strip()
        else:
            raw = raw.strip()
        if raw:
            return raw
    return peer or "unknown"


def _is_proxy(peer: str) -> bool:
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return False
    return address.is_private or address.is_loopback
