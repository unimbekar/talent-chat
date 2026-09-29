"""Turn parser output plus one model call into a stored profile."""

import re

from app.core.clearance import (
    CLEARANCE_ORDER,
    POLY_ORDER,
    higher_level,
    is_clearance_only,
    levels_from_text,
    map_phrase,
)
from app.core.detail_parser import DetailParse
from app.core.llm import LLMClient, LLMError, parse_json_content
from app.core.redact import redact_ssn
from app.core.locations import find_location_in_text
from app.core.skills import find_canonicals, normalize_skill_list, tools_and_languages
from app.core.us_states import looks_like_city, state_from_location

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?<!\d)(?:\+?1[\s.\-]?)?(?:\(\d{3}\)|\d{3})[\s.\-]?\d{3}[\s.\-]?\d{4}(?!\d)")
_CITY_STATE = re.compile(r"\b([A-Z][A-Za-z]+(?:[ \-][A-Z][A-Za-z]+)*),\s*([A-Z]{2})\b")
_ZIP_AFTER = re.compile(r"\s*(\d{5})(?:-\d{4})?\b")
HEADER_LINES = 15
_NAME_LINE = re.compile(r"^[A-Z][a-z]+(?:[ \-][A-Z][a-z]+){1,3}$")
_NAME_LEAD = re.compile(r"^([A-Z][a-z]+(?:[ \-][A-Z][a-z]+){1,3})\b")
_ROLE = re.compile(
    r"\b((?:senior|lead|principal|staff|mid[- ]level)\s+)?([A-Za-z][A-Za-z/& ]{0,40}?"
    r"(?:engineer|developer|architect|scientist|administrator|analyst|manager|consultant|tester))\b",
    re.I,
)
_SECTION = re.compile(
    r"(?i)^(skills|technical skills|core competencies|technologies|summary|professional summary|"
    r"experience|work experience|education|certifications|clearance)\s*:?\s*(.*)$"
)
_SUMMARY_HEADER = re.compile(r"(?i)^(summary|professional summary)$")
_YEARS = re.compile(
    r"(\d{1,2})\s*\+?\s*(?:years|yrs)\b.{0,48}\b(__SKILL__)\b|\b(__SKILL__)\b.{0,48}(\d{1,2})\s*\+?\s*(?:years|yrs)\b",
    re.I,
)


def resume_facts(text: str) -> dict:
    """Read contact fields, skills, and a short summary straight from résumé text."""
    raw = text or ""
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    email_match = _EMAIL.search(raw)
    phone_match = _PHONE.search(raw)
    return {
        "full_name": _resume_name(lines, raw),
        "email": email_match.group(0) if email_match else None,
        "phone": phone_match.group(0) if phone_match else None,
        "location": resume_location(raw),
        "skills": _resume_skills(raw, lines),
        "titles": _resume_titles(raw, lines),
        "citizenship": _resume_citizenship(raw),
        "summary": _resume_summary(lines, raw),
    }


def _resume_name(lines: list[str], text: str) -> str | None:
    for line in lines[:8]:
        if _EMAIL.search(line) or _PHONE.search(line) or "http" in line.lower():
            continue
        if line.lower() in {"resume", "curriculum vitae", "cv"}:
            continue
        if re.match(r"(?i)^(security clearance|clearance|education|experience|skills|technical skills|key competencies|professional certifications)\b", line):
            continue
        head = line.split(",")[0].strip()
        if head != line and _NAME_LINE.match(head) and not _ROLE.search(head):
            return head
        if _NAME_LINE.match(line) and not _ROLE.search(line):
            return line
        letters = re.sub(r"[^A-Za-z \-]", "", line)
        words = letters.split()
        if 1 < len(words) <= 4 and letters.isupper() and not _ROLE.search(line):
            return letters.title()
    lead = _NAME_LEAD.match(text.strip())
    if lead and not _ROLE.search(lead.group(1)):
        return lead.group(1)
    return None


def resume_location(text: str) -> str | None:
    """Home city from the résumé header: the name and contact lines.

    The body is not read. A city there is usually an employer, client, or program site,
    and filing that as home puts people in the wrong state. A 'City, ST' match counts only
    when ST is a real state and the city looks like a place.
    """
    raw = text or ""
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    header = "\n".join(lines[:HEADER_LINES])
    for match in _CITY_STATE.finditer(header):
        city = _trailing_city(match.group(1))
        if city is None:
            continue
        zip_code = _ZIP_AFTER.match(header, match.end())
        checked = f"{city}, {match.group(2)}" + (f" {zip_code.group(1)}" if zip_code else "")
        if state_from_location(checked):
            return f"{city}, {match.group(2)}"
    return find_location_in_text(header)


def _trailing_city(text: str) -> str | None:
    """Longest run of up to three final words that reads as a city.

    'Service System Administrator Oracle Reston' → 'Reston'. 'Fort Washington' stays whole.
    """
    words = text.split()
    best: str | None = None
    for size in range(1, min(3, len(words)) + 1):
        tail = " ".join(words[-size:])
        if not looks_like_city(tail):
            break
        best = tail
    return best


def _resume_skills(text: str, lines: list[str]) -> list[dict]:
    del lines
    names = tools_and_languages(text)
    return [{"name": name, "years": _years_near(text, name)} for name in names]


def _years_near(text: str, skill: str) -> float | None:
    pattern = _YEARS.pattern.replace("__SKILL__", re.escape(skill))
    match = re.search(pattern, text, re.I)
    if not match:
        return None
    digits = next((group for group in match.groups() if group and group.isdigit()), None)
    return float(digits) if digits else None


def _resume_titles(text: str, lines: list[str]) -> list[str]:
    found: list[str] = []
    for line in lines[:12]:
        if len(line) > 80 or _EMAIL.search(line) or _PHONE.search(line):
            continue
        match = _ROLE.search(line)
        if match and len(line.split()) <= 8:
            found.append(_clean_title(match.group(0)))
    if not found:
        match = _ROLE.search(text[:500])
        if match:
            found.append(_clean_title(match.group(0)))
    return _unique(found)[:3]


def _clean_title(value: str) -> str:
    trimmed = re.sub(r"(?i)^(an?|the|as|is)\s+", "", value).strip()
    return " ".join(part.capitalize() if part.islower() else part for part in trimmed.split())


def _resume_citizenship(text: str) -> str | None:
    if re.search(r"(?i)\b(u\.?s\.?\s+citizen|united states citizen|us citizen)\b", text):
        return "US Citizen"
    return None


def _resume_summary(lines: list[str], text: str) -> str:
    section = _section_lines(lines, _SUMMARY_HEADER)
    source = " ".join(section) if section else ""
    if not source:
        skipped = True
        prose: list[str] = []
        for line in lines:
            if skipped and (_NAME_LINE.match(line) or _EMAIL.search(line) or _PHONE.search(line) or _CITY_STATE.search(line)):
                continue
            skipped = False
            if _SECTION.match(line) and not line.endswith("."):
                continue
            prose.append(line)
        source = " ".join(prose) or text
    words = source.split()
    return " ".join(words[:120])


def _section_lines(lines: list[str], header: re.Pattern[str]) -> list[str]:
    collected: list[str] = []
    active = False
    for line in lines:
        match = _SECTION.match(line)
        if match:
            if header.match(match.group(1)):
                active = True
                if match.group(2).strip():
                    collected.append(match.group(2).strip())
                continue
            if active:
                break
        elif active:
            collected.append(line)
    return collected

JOB_SYSTEM = """You normalize a job posting that was already split by a parser.
Return JSON only with keys must_have_skills, nice_to_have_skills, clearance_required, polygraph_required, location, summary.
summary is under 80 words and uses only facts in the text.
clearance_required and polygraph_required are null when the text does not state them.
Do not add skills that are not in the text. Clearance phrases are not skills.
"""

RESUME_SYSTEM = """You extract a résumé profile. Return JSON only with keys
full_name, email, phone, location, skills, titles, clearance, polygraph, citizenship, summary.
skills is a list of objects {name, years} where years is a number or null.
Each skill name is one tool or one programming language, not a sentence or a duty.
clearance and polygraph are the raw phrase or null when unstated.
summary is under 120 words and uses only résumé facts.
Do not invent employers, degrees, or skills.
"""


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def skills_from_quotes(quotes: list[str]) -> list[str]:
    found: list[str] = []
    for quote in quotes:
        if not quote or is_clearance_only(quote):
            continue
        found.extend(find_canonicals(quote))
    return _unique(found)


def structure_job(parsed: DetailParse, llm: LLMClient) -> dict:
    description = redact_ssn(parsed.description_text or "")
    parser_must = skills_from_quotes(parsed.must_have_quotes)
    parser_nice = skills_from_quotes(parsed.nice_to_have_quotes)
    allowed = set(find_canonicals(description)) | set(parser_must) | set(parser_nice)
    prompt = (
        "Parser split:\n"
        f"description:\n{description[:6000]}\n\n"
        f"must_have_quotes: {parsed.must_have_quotes[:12]}\n"
        f"nice_to_have_quotes: {parsed.nice_to_have_quotes[:12]}\n"
        f"clearance_required: {parsed.clearance_required}\n"
        f"polygraph_required: {parsed.polygraph_required}\n"
    )
    data: dict = {}
    try:
        raw = llm.complete(system=JOB_SYSTEM, user=prompt, temperature=0.0, json_mode=True)
        data = parse_json_content(raw)
    except (LLMError, ValueError, TypeError):
        data = {}

    model_must = [
        skill
        for skill in normalize_skill_list(_as_str_list(data.get("must_have_skills")))
        if skill in allowed
    ]
    model_nice = [
        skill
        for skill in normalize_skill_list(_as_str_list(data.get("nice_to_have_skills")))
        if skill in allowed
    ]
    summary = data.get("summary") if isinstance(data.get("summary"), str) else ""
    summary = " ".join(summary.split())
    if len(summary.split()) > 80:
        summary = " ".join(summary.split()[:80])
    clearance = parsed.clearance_required
    poly = parsed.polygraph_required
    if clearance is None:
        clearance = _model_level(data.get("clearance_required"), "clearance")
    if poly is None:
        poly = _model_level(data.get("polygraph_required"), "polygraph")
    return {
        "description_text": description,
        "must_have_skills": _unique(parser_must + model_must),
        "nice_to_have_skills": _unique(parser_nice + model_nice),
        "clearance_required": clearance,
        "polygraph_required": poly,
        "summary": summary,
        "skill_quotes": {
            "must": [quote for quote in parsed.must_have_quotes if not is_clearance_only(quote)],
            "nice": [quote for quote in parsed.nice_to_have_quotes if not is_clearance_only(quote)],
            "clearance": parsed.clearance_quote,
        },
        "needs_review": parsed.needs_review,
    }


def parse_resume_profile(redacted_text: str, llm: LLMClient) -> dict:
    """Map clearance from the model phrase and from the résumé text. Highest level wins.

    When the model is down or leaves a field empty, fill that field from the résumé text
    so the review screen still shows a profile the recruiter can correct.
    """
    try:
        raw = llm.complete(
            system=RESUME_SYSTEM,
            user=redacted_text[:12000],
            temperature=0.0,
            json_mode=True,
        )
        data = parse_json_content(raw)
    except (LLMError, ValueError, TypeError):
        data = {}
    facts = resume_facts(redacted_text)
    skills = []
    for item in data.get("skills") or []:
        if isinstance(item, str):
            skills.append({"name": item, "years": None})
        elif isinstance(item, dict) and item.get("name"):
            years = item.get("years")
            skills.append({"name": str(item["name"]), "years": years if isinstance(years, (int, float)) else None})
    names = tools_and_languages("\n".join(skill["name"] for skill in skills))
    years_by_name = {skill["name"].lower(): skill["years"] for skill in skills}
    skill_rows = [{"name": name, "years": years_by_name.get(name.lower())} for name in names]
    if not skill_rows:
        skill_rows = facts["skills"]
    text_clearance, text_poly = levels_from_text(redacted_text)
    model_clearance = map_phrase(_optional_str(data.get("clearance")), "clearance")
    model_poly = map_phrase(_optional_str(data.get("polygraph")), "polygraph")
    clearance = higher_level(text_clearance, model_clearance, CLEARANCE_ORDER)
    poly = higher_level(text_poly, model_poly, POLY_ORDER)
    summary = data.get("summary") if isinstance(data.get("summary"), str) else ""
    words = summary.split()
    if len(words) > 120:
        summary = " ".join(words[:120])
    titles = [str(title) for title in (data.get("titles") or []) if str(title).strip()]
    return {
        "full_name": _optional_str(data.get("full_name")) or facts["full_name"],
        "email": _optional_str(data.get("email")) or facts["email"],
        "phone": _optional_str(data.get("phone")) or facts["phone"],
        "location": _optional_str(data.get("location")) or facts["location"],
        "skills": skill_rows,
        "titles": titles or facts["titles"],
        "clearance": clearance,
        "polygraph": poly,
        "citizenship": _optional_str(data.get("citizenship")) or facts["citizenship"],
        "summary": summary or facts["summary"],
    }


def _optional_str(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_str_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _model_level(value, kind: str) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "null":
        return None
    if text in {"none", "public_trust", "secret", "ts", "ts_sci", "ci", "full_scope", "unknown"}:
        return text
    return map_phrase(text, kind)
