"""Refusal runs before any database call."""

import re

_REFUSAL = re.compile(
    r"(?i)(\bcandidates?\b|\brésumés?\b|\bresumes?\b|\bphone numbers?\b|"
    r"\bemail addresses?\b|\bemails?\b|who applied|who do you have|clearance roster)"
)

REFUSAL_TEXT = "The assistant can search published jobs only."


def is_refusal(message: str) -> bool:
    return bool(_REFUSAL.search(message or ""))
