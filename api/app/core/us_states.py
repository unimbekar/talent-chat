"""US states and postal codes. Files a candidate's home state and reads states from a question."""

from __future__ import annotations

import re

STATES: dict[str, str] = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "DC": "District of Columbia",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
}

_BY_NAME = {name.lower(): code for code, name in STATES.items()}

# Two-letter codes that are also ordinary English words. In a question they count
# only when written in capitals next to a place word, never on their own.
_WORD_CODES = {"IN", "OR", "ME", "OK", "HI", "ID", "OH", "DE", "LA", "MA", "PA", "AL"}

# Words that mark the text before ", ST" as an employer, school, or role rather than a city.
_NOT_A_CITY = {
    "university",
    "college",
    "school",
    "institute",
    "academy",
    "inc",
    "llc",
    "corp",
    "corporation",
    "company",
    "technologies",
    "technology",
    "solutions",
    "services",
    "service",
    "system",
    "systems",
    "administrator",
    "engineer",
    "developer",
    "analyst",
    "manager",
    "oracle",
    "agency",
    "department",
    "center",
    "group",
    # Product names written before ", MS" (Microsoft), not Mississippi.
    "lotus",
    "notes",
    "office",
    "server",
    "studio",
    "exchange",
    "visio",
    "windows",
    "azure",
    "sharepoint",
    "dynamics",
    "outlook",
    "excel",
    # Street words, so "Storch Ct Lanham" reads as Lanham.
    "ct",
    "st",
    "ave",
    "rd",
    "dr",
    "ln",
    "blvd",
    "pl",
    "cir",
    "ter",
    "pkwy",
    "hwy",
    "apt",
    "suite",
    "court",
    "street",
    "avenue",
    "road",
    "drive",
    "lane",
}

# Words that finish a city name but are not one alone: "Jersey City", not "City".
_NOT_ALONE = {"city", "town", "county", "park", "beach", "springs", "falls", "heights", "hills"}

# ", MS" after a word is usually Microsoft on a résumé. Mississippi counts only with a ZIP code.
_NEEDS_ZIP = {"MS"}

_ZIP = re.compile(r"\s*\d{5}(?:-\d{4})?\s*$")
_DC = re.compile(r"(?i)\b(?:washington\s*,?\s*d\.?\s*c\.?|district\s+of\s+columbia)\b")


def state_code(value: str | None) -> str | None:
    """Map 'MD', 'md', or 'Maryland' to 'MD'. Anything else is None."""
    text = re.sub(r"[.\s]+", " ", (value or "")).strip()
    if not text:
        return None
    if len(text) == 2 and text.upper() in STATES:
        return text.upper()
    return _BY_NAME.get(text.lower())


def state_name(code: str) -> str:
    return STATES.get(code, code)


def looks_like_city(text: str) -> bool:
    words = text.split()
    if not 1 <= len(words) <= 3:
        return False
    if len(words) == 1 and words[0].lower() in _NOT_ALONE:
        return False
    for word in words:
        bare = word.strip(".'-")
        if not bare or not re.fullmatch(r"[A-Za-z][A-Za-z.'\-]*", bare):
            return False
        if bare.lower() in _NOT_A_CITY:
            return False
        if bare.isupper() and len(bare) < 5:
            return False
        if not bare.isupper() and not bare[0].isupper():
            return False
    return True


def state_from_location(location: str | None) -> str | None:
    """Home state for a stored location such as 'Largo, MD' or 'Baltimore, Maryland 21201'.

    Returns None when the text is not clearly a US place, for example 'PAT, IP',
    'CACI, VA', or 'Maryland, DC'. An empty state is better than a wrong one.
    """
    text = (location or "").strip()
    if not text:
        return None
    if _DC.search(text):
        return "DC"
    if "," in text:
        city, _, tail = text.rpartition(",")
        city = city.strip()
        has_zip = bool(_ZIP.search(tail))
        tail = _ZIP.sub("", tail).strip()
        code = state_code(tail)
        if code is None:
            return None
        if code in _NEEDS_ZIP and len(tail) == 2 and not has_zip:
            return None
        if state_code(city) is not None:
            return None
        return code if looks_like_city(city) else None
    whole = state_code(_ZIP.sub("", text))
    if whole:
        return whole
    match = re.fullmatch(r"(.+?)\s+([A-Za-z]{2})", _ZIP.sub("", text))
    if match and match.group(2).isupper() and match.group(2) in STATES and looks_like_city(match.group(1)):
        return match.group(2)
    return None


def states_in_text(text: str) -> list[str]:
    """States a recruiter named in a question, in the order they appear.

    Full names always count ('Maryland', 'west virginia'). Capital postal codes count
    ('MD', 'VA'), except codes that are also English words, which count only after
    'in', 'from', or 'live in'.
    """
    raw = text or ""
    found: list[tuple[int, str]] = []
    taken = [False] * len(raw)

    def claim(start: int, end: int, code: str) -> None:
        if any(taken[start:end]):
            return
        taken[start:end] = [True] * (end - start)
        found.append((start, code))

    for match in _DC.finditer(raw):
        claim(match.start(), match.end(), "DC")
    for name, code in sorted(_BY_NAME.items(), key=lambda row: len(row[0]), reverse=True):
        for match in re.finditer(rf"(?i)(?<![A-Za-z]){re.escape(name)}(?![A-Za-z])", raw):
            claim(match.start(), match.end(), code)
    for match in re.finditer(r"(?<![A-Za-z])([A-Z]{2})(?![A-Za-z])", raw):
        code = match.group(1)
        if code not in STATES:
            continue
        if code in _WORD_CODES:
            before = raw[: match.start()].lower().rstrip(" ,")
            if not re.search(r"\b(in|from|near|live in|lives in|living in|based in)$", before):
                continue
        claim(match.start(), match.end(), code)
    ordered: list[str] = []
    for _pos, code in sorted(found):
        if code not in ordered:
            ordered.append(code)
    return ordered
