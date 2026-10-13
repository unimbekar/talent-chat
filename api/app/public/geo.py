"""City-level place for a visitor IP. Private addresses stay on the local network.

A public address is looked up once and remembered. The lookup names a city, not a street.
"""

import ipaddress
import logging

import httpx

logger = logging.getLogger("talent")

Place = tuple[str | None, str | None, str | None]
_CACHE: dict[str, Place] = {}


def kind_of(ip: str) -> str:
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return "unknown"
    if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
        return "local"
    if address.is_global:
        return "public"
    return "unknown"


def lookup_public(ip: str) -> Place:
    """Ask a public directory for the city of a global address. Empty when it does not answer."""
    try:
        response = httpx.get(f"https://ipwho.is/{ip}", timeout=2.5, follow_redirects=False)
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError):
        logger.info("place lookup did not answer for a visitor address")
        return (None, None, None)
    if not isinstance(data, dict) or not data.get("success"):
        return (None, None, None)
    return (_clip(data.get("city")), _clip(data.get("region")), _clip(data.get("country")))


def place_of(ip: str) -> Place:
    if kind_of(ip) != "public":
        return (None, None, None)
    cached = _CACHE.get(ip)
    if cached is not None:
        return cached
    found = lookup_public(ip)
    _CACHE[ip] = found
    return found


def location_label(ip: str, city: str | None, region: str | None, country: str | None) -> str:
    kind = kind_of(ip)
    if kind == "local":
        return "Local network"
    if kind != "public":
        return "Unknown"
    parts = [part for part in (city, region, country) if part]
    return ", ".join(parts) if parts else "Location unavailable"


def _clip(value) -> str | None:
    text = " ".join(str(value or "").split())
    return text[:80] or None
