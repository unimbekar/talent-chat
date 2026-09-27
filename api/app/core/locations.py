"""Known cities from configs/locations.yaml."""

from dataclasses import dataclass
from functools import lru_cache
import re

import yaml

from app.config import get_settings


@dataclass(frozen=True)
class Location:
    canonical: str
    aliases: tuple[str, ...]


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


@lru_cache
def load_locations() -> tuple[Location, ...]:
    path = get_settings().locations_path()
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    out: list[Location] = []
    for row in raw["locations"]:
        aliases = tuple(_norm(a) for a in row["aliases"])
        out.append(Location(canonical=row["canonical"], aliases=aliases))
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
