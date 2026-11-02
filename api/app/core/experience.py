"""Years of experience for a requirement the résumé already covers.

A stated figure on the résumé ("8 years of Java") and the dates of roles that
name the skill are both read. The higher of the two is kept. Nothing is
invented when neither source is present.
"""

from __future__ import annotations

from datetime import date
import re

from app.core.score import _any_tool_satisfies, _prose_matches, _required_tools
from app.core.skills import TOOL_CATALOG, _pattern, aliases_for, tools_and_languages


_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}
_MONTH = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)
_YEAR = r"(?:19|20)\d{2}"
_OPEN = r"(?:present|current|now|ongoing|today)"
_SEP = r"\s*(?:–|—|-|to)\s*"
_RANGE = re.compile(
    rf"(?ix)(?<!\d)(?:(?P<m1>{_MONTH})[.,]?\s+)?(?P<y1>{_YEAR}){_SEP}"
    rf"(?:(?:(?P<m2>{_MONTH})[.,]?\s+)?(?P<y2>{_YEAR})|(?P<open>{_OPEN}))(?!\d)"
)
_NUM_RANGE = re.compile(
    rf"(?ix)(?<!\d)(?P<m1>0?[1-9]|1[0-2])/(?P<y1>{_YEAR}){_SEP}"
    rf"(?:(?P<m2>0?[1-9]|1[0-2])/(?P<y2>{_YEAR})|(?P<open>{_OPEN}))(?!\d)"
)
_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
}
_QTY = (
    r"(\d{1,2}(?:\.\d)?|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)"
)
_YRS = r"(?:years|yrs)\b"
_DEGREE = re.compile(r"(?i)\b(bachelor|b\.s\.?|b\.a\.?|master'?s|m\.s\.?|m\.a\.?|ph\.?d|doctorate|degree)\b")
_SECTION = re.compile(r"(?i)^(experience|work experience|professional experience|employment|education)\b")


def annotate(resume_text: str, lines: list[str], today: date | None = None) -> list[dict]:
    """One record per covered line. years is null when the résumé does not support a number."""
    today = today or date.today()
    text = resume_text or ""
    stints = employment_stints(text, today)
    return [_one(text, stints, line, today) for line in lines]


def employment_stints(text: str, today: date) -> list[tuple[date, date, str]]:
    """Dated roles. The title line above a date range is part of that role."""
    spans = []
    for pattern in (_RANGE, _NUM_RANGE):
        for match in pattern.finditer(text or ""):
            start = _as_date(match, "m1", "y1", today, start=True)
            end = today if match.group("open") else _as_date(match, "m2", "y2", today, start=False)
            if start is None or end is None or end < start:
                continue
            spans.append((match.start(), match.end(), start, end))
    spans.sort()
    kept: list[tuple[int, int, date, date]] = []
    for span in spans:
        if kept and span[0] < kept[-1][1]:
            continue
        kept.append(span)
    stints: list[tuple[date, date, str]] = []
    for index, (start, _end_index, opened, closed) in enumerate(kept):
        body_from = _stint_start(text, start)
        body_to = _stint_start(text, kept[index + 1][0]) if index + 1 < len(kept) else len(text)
        if body_to < body_from:
            body_to = kept[index + 1][0]
        stints.append((opened, closed, text[body_from:body_to]))
    return stints


def _one(text: str, stints: list[tuple[date, date, str]], line: str, today: date) -> dict:
    tools = _required_tools(line, tools_and_languages(line))
    if not tools and _DEGREE.search(line or ""):
        return _record(line, None, "degree", "Education line. Years are not counted.", "Degree")
    if not tools:
        years = _union_years([(opened, closed) for opened, closed, body in stints if _prose_matches(line, body)])
        basis = "roles" if years is not None else None
        return _record(line, years, basis, _basis_detail(basis), _years_label(years) if years is not None else "Years not on résumé")
    alternatives = _any_tool_satisfies(line, tools)
    parts = [(tool, *skill_years(text, stints, tool, today)) for tool in tools]
    known = [(tool, years, basis) for tool, years, basis in parts if years is not None]
    detail = _parts_detail(parts) if len(parts) > 1 else ""
    if not known:
        return _record(line, None, None, detail or _basis_detail(None), "Years not on résumé")
    if alternatives:
        _tool, years, basis = max(known, key=lambda item: item[1])
        if not detail:
            detail = _basis_detail(basis)
        elif len(known) > 1:
            detail = f"{detail}. The longer stretch is shown."
        return _record(line, years, basis, detail, _years_label(years))
    if len(known) < len(parts):
        return _record(line, None, "partial", detail, _parts_label(parts))
    years = min(item[1] for item in known)
    basis = known[0][2] if len({item[2] for item in known}) == 1 else "roles"
    if len(parts) > 1:
        detail = f"{detail}. The shorter stretch is shown."
    else:
        detail = _basis_detail(basis)
    return _record(line, years, basis, detail, _years_label(years))


def skill_years(
    text: str,
    stints: list[tuple[date, date, str]],
    skill: str,
    today: date,
) -> tuple[float | None, str | None]:
    stated = stated_years(text, skill, today)
    roles = _union_years([(opened, closed) for opened, closed, body in stints if _mentions(body, skill)])
    if stated is None and roles is None:
        return None, None
    if roles is None or (stated is not None and stated >= roles):
        return stated, "stated"
    return roles, "roles"


def stated_years(text: str, skill: str, today: date) -> float | None:
    """A number the résumé itself gives for this skill, including 'since 2018'."""
    best: float | None = None
    for needle in _needles(skill):
        escaped = re.escape(needle)
        numbered = re.compile(
            rf"(?i)\b(?:over|more than|nearly|almost)?\s*{_QTY}\s*\+?\s*{_YRS}\s+"
            rf"(?:of\s+(?:experience\s+(?:with|in|using)\s+)?)?{escaped}\b"
            rf"|\b{escaped}\b\s*[,:(]\s*{_QTY}\s*\+?\s*{_YRS}"
        )
        for match in numbered.finditer(text or ""):
            value = _quantity(match)
            if value is not None:
                best = value if best is None else max(best, value)
        since = re.compile(rf"(?i)\bsince\s+({_YEAR})\b")
        for sentence in re.split(r"[\n.!?]+", text or ""):
            if not _pattern(needle).search(sentence):
                continue
            found = since.search(sentence)
            if not found:
                continue
            value = _since(int(found.group(1)), today)
            if value is not None:
                best = value if best is None else max(best, value)
    return best


def _needles(skill: str) -> list[str]:
    names = aliases_for(skill)
    folded = {name.lower() for name in names}
    for alias, display in TOOL_CATALOG:
        if display.lower() == skill.lower() and alias.lower() not in folded:
            names.append(alias)
            folded.add(alias.lower())
    names.sort(key=len, reverse=True)
    return names or [skill]


def _mentions(text: str, skill: str) -> bool:
    return any(_pattern(needle).search(text or "") for needle in _needles(skill))


def _quantity(match: re.Match[str]) -> float | None:
    for group in match.groups():
        if not group:
            continue
        if group.lower() in _WORDS:
            return float(_WORDS[group.lower()])
        try:
            value = float(group)
        except ValueError:
            continue
        if 0 < value <= 40:
            return value
    return None


def _since(year: int, today: date) -> float | None:
    if year > today.year or today.year - year > 40:
        return None
    return _round_years((today - date(year, 1, 1)).days / 365.25)


def _as_date(match: re.Match[str], month_key: str, year_key: str, today: date, *, start: bool) -> date | None:
    year_text = match.group(year_key)
    if not year_text:
        return None
    year = int(year_text)
    month_text = match.group(month_key)
    if month_text:
        month = _month_number(month_text)
        if month is None:
            return None
        if year == today.year and month > today.month:
            month = today.month
        return date(year, month, 1)
    month = 7
    if not start and year == today.year and month > today.month:
        return today
    if year == today.year and month > today.month:
        return date(year, today.month, 1)
    try:
        return date(year, month, 1)
    except ValueError:
        return None


def _month_number(text: str) -> int | None:
    token = text.lower().rstrip(".")
    if token.isdigit():
        value = int(token)
        return value if 1 <= value <= 12 else None
    return _MONTHS.get(token)


def _stint_start(text: str, index: int) -> int:
    line_start = text.rfind("\n", 0, index) + 1
    if line_start == 0:
        return 0
    previous = text.rfind("\n", 0, line_start - 1) + 1
    title = text[previous:line_start].strip()
    if not title or _SECTION.match(title) or _RANGE.search(title) or _NUM_RANGE.search(title):
        return line_start
    return previous


def _union_years(ranges: list[tuple[date, date]]) -> float | None:
    if not ranges:
        return None
    ordered = sorted(ranges)
    merged: list[list[date]] = [[ordered[0][0], ordered[0][1]]]
    for start, end in ordered[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    days = sum((end - start).days for start, end in merged)
    if days <= 0:
        return 0.5
    return _round_years(days / 365.25)


def _round_years(value: float) -> float:
    half = round(value * 2) / 2
    return max(0.5, min(40.0, half))


def _years_label(years: float) -> str:
    number = int(years) if float(years).is_integer() else years
    unit = "yr" if number == 1 else "yrs"
    return f"{number:g} {unit}" if isinstance(number, float) else f"{number} {unit}"


def _parts_label(parts: list[tuple[str, float | None, str | None]]) -> str:
    bits = []
    for tool, years, _basis in parts:
        bits.append(f"{tool} {_years_label(years)}" if years is not None else f"{tool} not stated")
    return " · ".join(bits)


def _parts_detail(parts: list[tuple[str, float | None, str | None]]) -> str:
    bits = []
    for tool, years, basis in parts:
        if years is None:
            bits.append(f"{tool} is not given as a length")
        else:
            bits.append(f"{tool} {_years_label(years)} ({_source(basis)})")
    return " · ".join(bits)


def _source(basis: str | None) -> str:
    if basis == "stated":
        return "stated on the résumé"
    if basis == "roles":
        return "from role dates"
    return "estimated"


def _basis_detail(basis: str | None) -> str:
    if basis == "stated":
        return "Taken from a years figure on the résumé."
    if basis == "roles":
        return "Taken from the dates of roles that name this."
    return "The résumé covers this line and does not say how long."


def _record(line: str, years: float | None, basis: str | None, detail: str, label: str) -> dict:
    return {"line": line, "years": years, "basis": basis, "detail": detail, "label": label}
