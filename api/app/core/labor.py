"""Labor categories taken from a résumé headline and filename.

The opening of the résumé is the primary signal. The filename adds a role when
it names one, such as Full Stack or DevOps. At most two categories are kept.
"""

from __future__ import annotations

import re

# Canonical name, then phrases that identify it in a résumé or a question.
_CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Software Tester", ("software tester", "qa tester", "qa engineer", "quality assurance", "test engineer", "senior tester")),
    ("CyberSecurity Engineer", ("cybersecurity engineer", "cyber security engineer", "cybersecurity", "cyber security", "security engineer", "security analyst", "cyber threat", "information security", "penetration testing")),
    ("DevOps Engineer", ("devops engineer", "dev ops engineer", "site reliability")),
    ("Cloud Engineer", ("cloud engineer", "cloud developer")),
    ("Data Scientist", ("data scientist", "data engineer", "machine learning engineer")),
    ("AI Engineer", ("ai engineer", "artificial intelligence", "machine learning", "ml engineer")),
    ("Salesforce Engineer", ("salesforce", "sfdc")),
    ("Service Now Engineer", ("service now", "servicenow")),
    ("Network Engineer", ("network engineer", "network administrator")),
    ("Systems Admin", ("system administrator", "systems administrator", "systems admin")),
    ("Database Engineer", ("database engineer", "database administrator")),
    ("Software Architect", ("software architect", "solutions architect", "solution architect")),
    ("Web Developer", ("web developer", "frontend engineer", "front end engineer", "front-end engineer", "backend engineer", "back end engineer")),
    ("Software Engineer", ("software engineer", "software developer", "full stack", "fullstack", "full-stack")),
    ("Project Manager", ("project manager", "program manager")),
    ("Systems Analyst", ("business analyst", "systems analyst")),
    ("Systems Engineer", ("systems engineer", "system engineer")),
    ("Project Integrator", ("project integrator",)),
    ("Documentation Specialist", ("technical writer", "documentation specialist")),
)

_GENERIC = {"Software Engineer"}


def labor_categories(filename: str, text: str) -> list[str]:
    header = (text or "")[:700]
    opening = header.splitlines()[0] if header else ""
    named = _match(filename or "")
    content = _match(header)
    hits = named | content
    if "Software Tester" in hits and "Project Manager" in hits and "project manager" not in opening.lower():
        hits.discard("Project Manager")
    if "CyberSecurity Engineer" in content and "Software Engineer" in hits and "Software Engineer" not in named:
        hits.discard("Software Engineer")
    if not hits:
        return []

    def score(category: str) -> tuple[int, int]:
        value = (10 if category in content else 0) + (8 if category in named else 0)
        if category in _GENERIC:
            value -= 4
        return (-value, _order(category))

    return sorted(hits, key=score)[:2]


def categories_for_question(message: str) -> list[str]:
    """Map a recruiter question onto labor categories."""
    return sorted(_match(message or ""), key=_order)


# Roles in one family can be scored against each other. A cybersecurity
# résumé is not scored as a data-scientist match.
_FAMILY = {
    "Data Scientist": "analytics",
    "AI Engineer": "analytics",
    "Software Engineer": "software",
    "Software Architect": "software",
    "Web Developer": "software",
    "Cloud Engineer": "platform",
    "DevOps Engineer": "platform",
    "Systems Engineer": "systems",
    "Systems Admin": "systems",
    "Systems Analyst": "systems",
}


def candidate_roles(filename: str, text: str, titles: list[str] | None = None) -> list[str]:
    """Every labor category named by the file, the opening, or the saved titles."""
    header = (text or "")[:700]
    hits = _match(filename or "") | _match(header)
    for title in titles or []:
        hits |= _match(title)
    return sorted(hits, key=_order)


def role_conflict(filename: str, text: str, titles: list[str] | None, job_title: str | None) -> list[str]:
    """Job roles when this résumé belongs to a different family. Empty when scoring can proceed."""
    job_roles = categories_for_question(job_title or "")
    roles = candidate_roles(filename, text, titles)
    if not job_roles or not roles:
        return []
    job_families = {_FAMILY.get(role, role) for role in job_roles}
    if any(_FAMILY.get(role, role) in job_families for role in roles):
        return []
    return job_roles


def _match(text: str) -> set[str]:
    folded = re.sub(r"[^a-z0-9]+", " ", (text or "").lower())
    compact = folded.replace(" ", "")
    hits: set[str] = set()
    for category, phrases in _CATEGORIES:
        for phrase in phrases:
            if phrase in folded or phrase.replace(" ", "") in compact:
                hits.add(category)
                break
    return hits


def _order(category: str) -> int:
    for index, (name, _phrases) in enumerate(_CATEGORIES):
        if name == category:
            return index
    return 99
