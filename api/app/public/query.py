"""Deterministic public query parsing. The model does not invent the filter."""

from dataclasses import dataclass, field
import re

from app.core.locations import Location, find_location_in_text
from app.core.skills import aliases_for, find_canonicals

_STOP = {
    "a", "an", "the", "and", "or", "with", "in", "of", "for", "to", "jobs", "job",
    "open", "what", "is", "are", "me", "about", "which", "these", "those", "who",
    "find", "show", "list", "on", "at", "va", "please", "any", "there", "do", "you",
    "have", "tell", "looking", "position", "positions", "role", "roles",
    "all", "every", "everything", "available", "current", "currently",
    "opening", "openings", "posted",
}
_CODE = re.compile(r"\b[A-Z][0-9]{3,5}\b")
_FOLLOW = re.compile(r"(?i)\b(these|those|them|which of)\b")
_SENIOR = re.compile(r"(?i)\bsenior\b")


@dataclass
class ParsedQuery:
    skills: list[str] = field(default_factory=list)
    skill_aliases: dict[str, list[str]] = field(default_factory=dict)
    city: str | None = None
    codes: list[str] = field(default_factory=list)
    fts: str = ""
    prior_only: bool = False
    senior_only: bool = False
    ask_clearance: bool = False
    ask_posting_fact: bool = False


def parse_query(
    message: str,
    synonyms: list[tuple[str, str]],
    locations: tuple[Location, ...],
    prior_codes: list[str] | None = None,
) -> ParsedQuery:
    text = message or ""
    parsed = ParsedQuery()
    parsed.codes = _CODE.findall(text)
    parsed.skills = find_canonicals(text, synonyms)
    parsed.skill_aliases = {skill: aliases_for(skill, synonyms) for skill in parsed.skills}
    parsed.city = find_location_in_text(text, locations)
    parsed.senior_only = bool(_SENIOR.search(text))
    parsed.ask_clearance = bool(re.search(r"(?i)\b(clearance|polygraph)\b", text))
    parsed.ask_posting_fact = bool(re.search(r"(?i)\b(salary|benefits|citizenship|visa|sponsor)\b", text))
    if prior_codes and _FOLLOW.search(text):
        parsed.prior_only = True
    consumed = set()
    for aliases in parsed.skill_aliases.values():
        for alias in aliases:
            consumed.add(alias.lower())
    if parsed.city:
        consumed.update(parsed.city.lower().replace(",", " ").split())
    words = []
    for word in re.findall(r"[A-Za-z0-9+./#-]+", text):
        token = word.lower().strip(".")
        if token in _STOP or token in consumed or _CODE.fullmatch(word):
            continue
        words.append(word)
    parsed.fts = " ".join(words)
    return parsed
