"""Clearance and polygraph synonym table. Never a reason to reject a file."""

import re

_TS_SCI = re.compile(
    r"TS\s*/\s*SCI|TS\s*-\s*SCI|Top\s+Secret\s*/\s*SCI|Top\s+Secret\s+SCI",
    re.I,
)
_TOP_SECRET = re.compile(r"Top\s+Secret(?!\s*/\s*SCI)(?!\s+SCI\b)", re.I)
_TS_STANDALONE = re.compile(r"\bTS\b(?!\s*/\s*SCI)(?!\s*-\s*SCI)", re.I)
_SECRET = re.compile(r"(?<!\bTop\s)\bSecret\b", re.I)
_PUBLIC_TRUST = re.compile(r"Public\s+Trust", re.I)
_FULL_SCOPE = re.compile(
    r"Full[\s-]*Scope\s+Poly(?:graph)?|Lifestyle\s+Poly(?:graph)?|\bFSP\b",
    re.I,
)
_CI_POLY = re.compile(r"\bCI\s+Poly(?:graph)?\b|Counterintelligence\s+Polygraph", re.I)
_POLY_ALONE = re.compile(r"\bPoly(?:graph)?\b", re.I)

CLEARANCE_ORDER = ["none", "public_trust", "secret", "ts", "ts_sci"]
POLY_ORDER = ["none", "ci", "full_scope"]

_CLEARANCE_FILLER = re.compile(
    r"(?i)\b(active|must|hold|with|an|a|the|and|or|clearance|security|top|secret|"
    r"ts|sci|polygraph|poly|full|scope|fsp|lifestyle|counterintelligence|ci|"
    r"public|trust|required|strictly|is)\b|[/:,.\-()]+"
)


def map_clearance_text(text: str | None) -> tuple[str | None, str | None]:
    """Map a phrase to (clearance, polygraph). Unstated stays None. Do not guess upward."""
    if text is None or not str(text).strip():
        return None, None
    clearance = None
    if _TS_SCI.search(text):
        clearance = "ts_sci"
    elif _TOP_SECRET.search(text) or _TS_STANDALONE.search(text):
        clearance = "ts"
    elif _SECRET.search(text):
        clearance = "secret"
    elif _PUBLIC_TRUST.search(text):
        clearance = "public_trust"

    poly = None
    if _FULL_SCOPE.search(text):
        poly = "full_scope"
    elif _CI_POLY.search(text):
        poly = "ci"
    elif _POLY_ALONE.search(text):
        poly = "unknown"
    return clearance, poly


def map_phrase(phrase: str | None, kind: str) -> str | None:
    """Map one model field. Non-empty text that matches nothing is unknown."""
    if phrase is None or not str(phrase).strip():
        return None
    clearance, poly = map_clearance_text(phrase)
    level = clearance if kind == "clearance" else poly
    if level is None:
        return "unknown"
    return level


def higher_level(current: str | None, new: str | None, order: list[str]) -> str | None:
    if new is None:
        return current
    if current is None:
        return new
    if current == "unknown" and new == "unknown":
        return "unknown"
    if current == "unknown":
        return new
    if new == "unknown":
        return current
    if current not in order or new not in order:
        return new
    return new if order.index(new) > order.index(current) else current


def levels_from_text(*parts: str | None) -> tuple[str | None, str | None]:
    clearance = None
    poly = None
    for part in parts:
        c, p = map_clearance_text(part)
        clearance = higher_level(clearance, c, CLEARANCE_ORDER)
        poly = higher_level(poly, p, POLY_ORDER)
    return clearance, poly


def is_clearance_only(text: str) -> bool:
    """True when the string is clearance wording and not a skill."""
    if not text or not text.strip():
        return False
    clearance, poly = map_clearance_text(text)
    if clearance is None and poly is None and not re.search(r"(?i)clearance|polygraph|top secret|ts/sci", text):
        return False
    if clearance is None and poly is None:
        return False
    residual = _CLEARANCE_FILLER.sub(" ", text)
    residual = re.sub(r"\s+", " ", residual).strip()
    return residual == ""


def clearance_flag(
    candidate_clearance: str | None,
    candidate_poly: str | None,
    job_clearance: str | None,
    job_poly: str | None,
) -> str | None:
    """Admin-only flag. Jobs stay visible either way."""
    short = False
    unknown = False
    if _requires(job_clearance):
        relation = _compare(candidate_clearance, job_clearance, CLEARANCE_ORDER)
        short = short or relation == "short"
        unknown = unknown or relation == "unknown"
    if _requires(job_poly):
        relation = _compare(candidate_poly, job_poly, POLY_ORDER)
        short = short or relation == "short"
        unknown = unknown or relation == "unknown"
    if short:
        return "clearance_short"
    if unknown:
        return "clearance_unknown"
    return None


def _requires(level: str | None) -> bool:
    return level not in (None, "", "none")


def _compare(candidate: str | None, required: str, order: list[str]) -> str:
    if candidate in (None, "", "unknown"):
        return "unknown"
    if candidate not in order or required not in order:
        return "unknown"
    if order.index(candidate) < order.index(required):
        return "short"
    return "ok"
