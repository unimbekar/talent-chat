"""Match a visitor's tool names against posting lines, including exclusions."""

import re

# A named tool also matches the way postings actually write it.
_FAMILY: dict[str, tuple[str, ...]] = {
    "spring boot": ("Spring Boot", "SpringBoot", "Spring Framework", "Spring"),
    "spring": ("Spring Framework", "Spring Boot", "SpringBoot", "Spring"),
    "machine learning": ("Machine Learning", "AI/ML", "ML"),
}

_EXCLUDE = re.compile(
    r"(?i)\b(?:explicitly\s+excluding|excluding|except(?:\s+for)?|without|other\s+than|not\s+including)\b"
)
_SPRING = {"spring boot", "spring"}


def phrase_variants(name: str) -> list[str]:
    family = _FAMILY.get(name.lower())
    if family:
        return list(family)
    compact = re.sub(r"\s+", "", name)
    if compact.lower() != name.lower():
        return [name, compact]
    return [name]


def phrase_groups(phrases: list[str]) -> list[list[str]]:
    """Tools the posting must name. Spring Boot and Spring are one group."""
    spring = [phrase for phrase in phrases if phrase.lower() in _SPRING]
    rest = [phrase for phrase in phrases if phrase.lower() not in _SPRING]
    groups: list[list[str]] = []
    if spring:
        groups.append(spring)
    groups.extend([phrase] for phrase in rest)
    return groups


def line_requires(line: str, variants: list[str]) -> bool:
    """True when a variant is named as a requirement, not only inside an exclusion."""
    text = line or ""
    ordered = sorted(variants, key=len, reverse=True)
    for variant in ordered:
        pattern = re.compile(rf"(?<!\w){re.escape(variant)}(?!\w)", re.I)
        for match in pattern.finditer(text):
            if not _excluded(text, match.start()):
                return True
    return False


def _excluded(text: str, index: int) -> bool:
    before = text[:index]
    lead = None
    for found in _EXCLUDE.finditer(before):
        lead = found
    if lead is None:
        return False
    gap = before[lead.end() :]
    return re.search(r"[.;\n]", gap) is None


def requirement_lines(job, *, required_only: bool) -> list[str]:
    quotes = job.skill_quotes or {}
    lines: list[str] = []
    for line in quotes.get("must") or []:
        if line and str(line).strip():
            lines.append(str(line).strip())
    for skill in job.must_have_skills or []:
        if skill:
            lines.append(str(skill))
    if job.title:
        lines.append(job.title)
    for part in re.split(r"\n+", job.description_text or ""):
        if part.strip():
            lines.append(part.strip())
    if required_only:
        return lines
    for line in quotes.get("nice") or []:
        if line and str(line).strip():
            lines.append(str(line).strip())
    for skill in job.nice_to_have_skills or []:
        if skill:
            lines.append(str(skill))
    return lines


def evidence_line(job, phrases: list[str], *, required_only: bool) -> str | None:
    """The posting line that satisfies every tool the visitor named."""
    groups = phrase_groups(phrases)
    if not groups:
        return None
    lines = requirement_lines(job, required_only=required_only)
    found: list[str] = []
    for group in groups:
        variants: list[str] = []
        for name in group:
            for variant in phrase_variants(name):
                if variant not in variants:
                    variants.append(variant)
        hit = next((line for line in lines if line_requires(line, variants)), None)
        if hit is None:
            return None
        found.append(hit)
    for line in found:
        if len(line) > 24:
            return line
    return found[0]
