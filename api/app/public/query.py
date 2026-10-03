"""Deterministic public query parsing. The model does not invent the filter."""

from dataclasses import dataclass, field
import re

from app.core.locations import Location, find_location_in_text, find_place_in_text
from app.core.skills import aliases_for, find_canonicals, tools_and_languages
from app.public.typos import normalize_query_typos

_STOP = {
    "a", "an", "the", "and", "or", "with", "in", "of", "for", "to", "jobs", "job",
    "open", "what", "is", "are", "me", "about", "which", "these", "those", "who",
    "find", "show", "list", "on", "at", "va", "please", "any", "there", "do", "you",
    "have", "tell", "looking", "position", "positions", "role", "roles",
    "all", "every", "everything", "available", "current", "currently",
    "opening", "openings", "posted",
    "would", "like", "see", "seen", "want", "wants", "wanted", "need", "needs",
    "needed", "get", "give", "could", "should", "help", "i", "im", "id", "ive",
    "we", "our", "my", "some", "just", "also", "really", "hi", "hello", "hey",
    "search", "searching", "know", "anyone", "anything", "something", "around",
    "near", "nearby", "based", "located", "location", "area", "only",
    "specifically", "specific", "that", "this", "they", "their", "here", "how",
    "many", "where", "when", "why", "will", "may", "might", "let", "lets", "us",
    "your", "kind", "type", "types", "related", "interested", "interest", "look",
    "can", "able",
    "require", "required", "requires", "requiring", "requirement", "requirements",
    "using", "use", "uses", "used", "experience", "experienced", "include",
    "including", "includes", "work", "working", "works", "mention", "mentions",
    "mentioning", "involve", "involves", "involving", "technology", "technologies",
    "skill", "skills", "proficient", "proficiency", "familiar", "familiarity",
    "background", "stack", "framework", "frameworks", "tool", "tools", "language",
    "languages", "developer", "developers", "engineer", "engineers", "must",
}
_CODE = re.compile(r"\b[A-Z][0-9]{3,5}\b")
_FOLLOW = re.compile(r"(?i)\b(these|those|them|which of)\b")
_SENIOR = re.compile(r"(?i)\bsenior\b")
_EXCLUDE_BEFORE = re.compile(
    r"(?:not(?:\s+in|\s+at)?|outside(?:\s+of)?|except(?:\s+for)?|other\s+than|besides|excluding|anywhere\s+but)\s*$"
)


@dataclass
class ParsedQuery:
    skills: list[str] = field(default_factory=list)
    skill_aliases: dict[str, list[str]] = field(default_factory=dict)
    city: str | None = None
    exclude_city: str | None = None
    near_place: str | None = None
    near_miles: float | None = None
    codes: list[str] = field(default_factory=list)
    phrases: list[str] = field(default_factory=list)
    fts: str = ""
    prior_only: bool = False
    senior_only: bool = False
    required_only: bool = False
    ask_clearance: bool = False
    ask_posting_fact: bool = False


def parse_query(
    message: str,
    synonyms: list[tuple[str, str]],
    locations: tuple[Location, ...],
    prior_codes: list[str] | None = None,
) -> ParsedQuery:
    text = normalize_query_typos(message or "", locations)
    parsed = ParsedQuery()
    parsed.codes = _CODE.findall(text)
    parsed.phrases = tools_and_languages(text)
    parsed.skills = find_canonicals(text, synonyms)
    parsed.required_only = bool(re.search(r"(?i)\b(require|required|requires|requiring|must|need|needs)\b", text))
    # "Spring Boot" is its own tool. It must not widen into every Java job
    # unless the visitor also said Java.
    if any(phrase.lower() in {"spring boot", "spring"} for phrase in parsed.phrases):
        if not re.search(r"(?i)(?<!\w)java(?!\w)", text):
            parsed.skills = [skill for skill in parsed.skills if skill.lower() != "java"]
    parsed.skill_aliases = {skill: aliases_for(skill, synonyms) for skill in parsed.skills}
    parsed.city = find_location_in_text(text, locations)
    if parsed.city and _city_is_excluded(text, parsed.city, locations):
        parsed.exclude_city = parsed.city
        parsed.city = None
    place = find_place_in_text(text)
    near_cue = re.search(r"(?i)\b(closest|nearest|near|nearby|within)\b", text)
    miles_of = re.search(r"(?i)\b(\d+(?:\.\d+)?)\s+(?:miles|mile|mi)\s+(?:of|from)\b", text)
    if place is not None and (near_cue or miles_of):
        parsed.near_place = place.name
        within = re.search(r"(?i)\bwithin\s+(\d+(?:\.\d+)?)", text)
        if within:
            parsed.near_miles = float(within.group(1))
        elif miles_of:
            parsed.near_miles = float(miles_of.group(1))
    parsed.senior_only = bool(_SENIOR.search(text))
    parsed.ask_clearance = bool(re.search(r"(?i)\b(clearance|polygraph)\b", text))
    parsed.ask_posting_fact = bool(re.search(r"(?i)\b(salary|benefits|citizenship|visa|sponsor)\b", text))
    if prior_codes and (_FOLLOW.search(text) or parsed.near_place):
        parsed.prior_only = True
    consumed = set()
    for aliases in parsed.skill_aliases.values():
        for alias in aliases:
            consumed.add(alias.lower())
    for phrase in parsed.phrases:
        consumed.update(phrase.lower().split())
    if parsed.city:
        consumed.update(parsed.city.lower().replace(",", " ").split())
    if parsed.exclude_city:
        consumed.update(parsed.exclude_city.lower().replace(",", " ").split())
        consumed.update({"not", "outside", "except", "other", "than", "besides", "excluding", "anywhere", "but"})
    if parsed.near_place:
        consumed.update(parsed.near_place.lower().replace(",", " ").split())
        consumed.update({
            "closest", "nearest", "near", "nearby", "within", "miles", "mile", "mi",
            "maryland", "md", "from", "of",
        })
        if parsed.near_miles is not None:
            consumed.add(str(int(parsed.near_miles)) if parsed.near_miles.is_integer() else str(parsed.near_miles))
    words = []
    for word in re.findall(r"[A-Za-z0-9+./#-]+", text):
        token = word.lower().strip(".")
        if token in _STOP or token in consumed or _CODE.fullmatch(word):
            continue
        words.append(word)
    # "all jobs not in McLean" is fully specified by the exclusion. A leftover
    # typo such as "thar" must not wipe that result.
    if parsed.exclude_city and not parsed.skills:
        words = []
    parsed.fts = " ".join(words)
    return parsed


def _city_is_excluded(text: str, city: str, locations: tuple[Location, ...]) -> bool:
    norm = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    for loc in locations:
        if loc.canonical != city:
            continue
        for alias in sorted(loc.aliases, key=len, reverse=True):
            start = 0
            while True:
                idx = norm.find(alias, start)
                if idx < 0:
                    break
                if _EXCLUDE_BEFORE.search(norm[:idx]):
                    return True
                start = idx + len(alias)
    return False
