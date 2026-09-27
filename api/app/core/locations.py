"""Known cities from configs/locations.yaml."""

from dataclasses import dataclass
from functools import lru_cache
import math
import re

import yaml

from app.config import get_settings


@dataclass(frozen=True)
class Location:
    canonical: str
    aliases: tuple[str, ...]
    latitude: float | None = None
    longitude: float | None = None


@dataclass(frozen=True)
class Place:
    name: str
    aliases: tuple[str, ...]
    latitude: float
    longitude: float


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


@lru_cache
def load_locations() -> tuple[Location, ...]:
    path = get_settings().locations_path()
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    out: list[Location] = []
    for row in raw["locations"]:
        aliases = tuple(_norm(a) for a in row["aliases"])
        out.append(
            Location(
                canonical=row["canonical"],
                aliases=aliases,
                latitude=row.get("latitude"),
                longitude=row.get("longitude"),
            )
        )
    return tuple(out)


@lru_cache
def load_places() -> tuple[Place, ...]:
    path = get_settings().locations_path()
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    out: list[Place] = []
    for row in raw.get("places") or []:
        out.append(
            Place(
                name=row["name"],
                aliases=tuple(_norm(a) for a in row["aliases"]),
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
            )
        )
    return tuple(out)


def match_location_segment(segment: str, locations: tuple[Location, ...] | None = None) -> str | None:
    """Match a listing city segment such as 'Mclean VA' to a canonical city."""
    locations = locations if locations is not None else load_locations()
    norm = _norm(segment)
    for loc in locations:
        if norm in loc.aliases:
            return loc.canonical
    return None


def find_location_in_text(text: str, locations: tuple[Location, ...] | None = None) -> str | None:
    """Find a city mentioned in a visitor question. Longest alias wins."""
    locations = locations if locations is not None else load_locations()
    norm = _norm(text)
    padded = f" {norm} "
    best: tuple[int, str] | None = None
    for loc in locations:
        for alias in loc.aliases:
            if f" {alias} " in padded:
                if best is None or len(alias) > best[0]:
                    best = (len(alias), loc.canonical)
    return best[1] if best else None


def find_place_in_text(text: str, places: tuple[Place, ...] | None = None) -> Place | None:
    """Find a reference place such as Bethesda. Longest alias wins."""
    places = places if places is not None else load_places()
    norm = _norm(text)
    padded = f" {norm} "
    best: tuple[int, Place] | None = None
    for place in places:
        for alias in place.aliases:
            if f" {alias} " in padded and (best is None or len(alias) > best[0]):
                best = (len(alias), place)
    return best[1] if best else None


def miles_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in miles."""
    radius = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    half = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    return radius * 2 * math.asin(math.sqrt(half))


def miles_from_place(place: Place, city: str | None, locations: tuple[Location, ...] | None = None) -> float | None:
    if not city:
        return None
    locations = locations if locations is not None else load_locations()
    for loc in locations:
        if loc.canonical == city and loc.latitude is not None and loc.longitude is not None:
            return miles_between(place.latitude, place.longitude, loc.latitude, loc.longitude)
    return None
