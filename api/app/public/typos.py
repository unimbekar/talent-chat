"""One-edit corrections for public search words.

The model writes the reply after jobs are found. It does not decide the filter,
so a misspelled word such as "withing" has to be repaired here.
"""

import re

from app.core.locations import Location, load_places
from app.core.skills import TOOL_CATALOG

# Words that steer the filter. A single extra, missing, swapped, or
# neighboring letter still counts as the word.
_INTENT = (
    "within",
    "closest",
    "nearest",
    "nearby",
    "miles",
    "clearance",
    "polygraph",
    "senior",
    "salary",
    "benefits",
    "citizenship",
    "sponsor",
    "require",
    "required",
    "requires",
    "requiring",
    "excluding",
)

# Ordinary words that sit one edit from a search word and must stay as typed.
_KEEP = {
    "string",
    "sprint",
    "sprung",
    "sensor",
    "scale",
    "spare",
    "shark",
    "doctor",
    "reach",
    "males",
    "moles",
    "mules",
    "milks",
    "closer",
    "willing",
    "working",
    "training",
    "during",
    "offering",
    "writing",
    "clearing",
    "leaning",
    "smiles",
    "files",
    "springy",
}


def normalize_query_typos(text: str, locations: tuple[Location, ...] = ()) -> str:
    """Replace a token that is one edit from exactly one known search word."""
    targets = _targets(locations)
    by_letter: dict[str, tuple[str, ...]] = {}
    for word in targets:
        by_letter.setdefault(word[0], []).append(word)
    buckets = {letter: tuple(words) for letter, words in by_letter.items()}

    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        low = token.lower()
        if len(low) < 5 or low in _KEEP or low in targets:
            return token
        bucket = buckets.get(low[0])
        if not bucket:
            return token
        fixed = _unique_edit(low, bucket)
        return fixed if fixed else token

    return re.sub(r"[A-Za-z]+", replace, text or "")


def _targets(locations: tuple[Location, ...]) -> set[str]:
    words = {word for word in _INTENT if len(word) >= 5}
    for alias, _display in TOOL_CATALOG:
        words.update(_long_words(alias))
    for loc in locations:
        for alias in loc.aliases:
            words.update(_long_words(alias))
    try:
        places = load_places()
    except Exception:
        places = ()
    for place in places:
        for alias in place.aliases:
            words.update(_long_words(alias))
    words.difference_update(_KEEP)
    return words


def _long_words(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z]{5,}", text.lower())}


def _unique_edit(token: str, targets: tuple[str, ...]) -> str | None:
    found: str | None = None
    for target in targets:
        if abs(len(token) - len(target)) > 1:
            continue
        if _edit_distance(token, target) != 1:
            continue
        if found is not None:
            return None
        found = target
    return found


def _edit_distance(left: str, right: str) -> int:
    """Insert, delete, substitute, or one adjacent transposition. Stops past 1."""
    if left == right:
        return 0
    if abs(len(left) - len(right)) > 1:
        return 2
    rows = len(left) + 1
    cols = len(right) + 1
    prev2 = [0] * cols
    prev = list(range(cols))
    for i in range(1, rows):
        cur = [i] + [0] * (cols - 1)
        smallest = cur[0]
        for j in range(1, cols):
            cost = 0 if left[i - 1] == right[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and left[i - 1] == right[j - 2] and left[i - 2] == right[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
            smallest = min(smallest, cur[j])
        if smallest > 1:
            return 2
        prev2 = prev
        prev = cur
    return prev[-1]
