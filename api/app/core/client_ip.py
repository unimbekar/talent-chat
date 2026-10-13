"""Client IP. Trust a proxy header only when the peer is a private proxy."""

import ipaddress

from app.config import Settings


def client_ip(request, settings: Settings) -> str:
    peer = ""
    if request.client and request.client.host:
        peer = _plain(request.client.host)
    header = (settings.trusted_proxy_header or "").strip()
    if header and _is_proxy(peer):
        raw = request.headers.get(header, "")
        if header.lower() == "x-forwarded-for":
            # The nearest proxy appends the address it actually saw. Earlier entries can be supplied by the client.
            hops = [part.strip() for part in raw.split(",") if part.strip()]
            raw = hops[-1] if hops else ""
        else:
            raw = raw.strip()
        if raw:
            return _plain(raw)
    return peer or "unknown"


def _plain(raw: str) -> str:
    text = raw.strip()
    if text.startswith("[") and "]" in text:
        text = text[1 : text.index("]")]
    if "%" in text:
        text = text.split("%", 1)[0]
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return text
    mapped = getattr(address, "ipv4_mapped", None)
    return str(mapped or address)


def _is_proxy(peer: str) -> bool:
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return False
    return address.is_private or address.is_loopback
