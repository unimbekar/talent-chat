"""Find candidates: the model reads the question, SQL applies the filters.

The model only turns the recruiter's sentence into filters. It never sees a résumé
and never chooses who is listed. Each filter it returns is checked against the
question before it is used, so a state or skill the recruiter did not ask for is
dropped. When the model is down, a rule parser reads the same filters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import nullslast

from app.core.labor import categories_for_question
from app.core.llm import LLMClient, LLMError, parse_json_content
from app.core.skills import aliases_for, find_canonicals, normalize_skill_list
from app.core.us_states import state_code, state_name, states_in_text
from app.models import Candidate

RESULT_LIMIT = 200

QUERY_SYSTEM = """You turn a recruiter's question about candidates into search filters.
Return JSON only with these keys:
  skills: tools, platforms, or programming languages the person must have, such as "ServiceNow" or "Java".
  states: US states where the person must live, as two-letter postal codes, such as "MD".
  exclude_states: US states where the person must not live, for questions such as "outside Virginia".
  cities: cities named in the question, as objects {"city": "Baltimore", "state": "MD"}.
  roles: job roles asked for, such as "Software Tester" or "Network Engineer". Only when the question names a role.
  keywords: other short phrases the résumé must contain, such as "machine learning". Usually empty.
Use only what the question says. Leave a list empty when the question does not ask for it.
A skill is not a role: "ServiceNow experience" is the skill ServiceNow, not the role ServiceNow Engineer.
Do not add related skills, nearby states, or roles the question does not name.
"""

_ROLE_WORD = re.compile(
    r"(?i)\b(engineers?|developers?|admins?|administrators?|architects?|testers?|analysts?|"
    r"managers?|scientists?|specialists?|consultants?|integrators?|writers?)\b"
)

# Aliases this short ("Go", "R") match ordinary words in résumé text, so they are
# matched only against the parsed skill list.
_MIN_TEXT_ALIAS = 3


@dataclass
class Filters:
    skills: list[str] = field(default_factory=list)
    states: list[str] = field(default_factory=list)
    exclude_states: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    parser: str = "rules"

    def empty(self) -> bool:
        return not (self.skills or self.states or self.exclude_states or self.categories or self.keywords)

    def as_dict(self) -> dict:
        return {
            "skills": self.skills,
            "states": [{"code": code, "name": state_name(code)} for code in self.states],
            "exclude_states": [{"code": code, "name": state_name(code)} for code in self.exclude_states],
            "categories": self.categories,
            "keywords": self.keywords,
            "parser": self.parser,
        }


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.lower()
        if item and key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _str_list(value) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _in_question(phrase: str, question: str) -> bool:
    fold = lambda text: re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()  # noqa: E731
    target = fold(phrase)
    return bool(target) and f" {target} " in f" {fold(question)} "


def rule_filters(question: str) -> Filters:
    """Read filters without the model: known skills, state names and codes, and role phrases.

    The rule parser does not understand negation. "Outside Virginia" becomes a Virginia
    filter here, which is why the model's reading is preferred when it is available.
    """
    skills = find_canonicals(question)
    categories = categories_for_question(question)
    if skills and not _ROLE_WORD.search(question):
        categories = []
    return Filters(
        skills=_unique(skills),
        states=states_in_text(question),
        categories=categories,
        keywords=[],
        parser="rules",
    )


def _grounded_states(values, named: set[str], cities: dict[str, str]) -> list[str]:
    out: list[str] = []
    for value in _str_list(values):
        code = state_code(value)
        if code and (code in named or code in cities.values()):
            out.append(code)
    return out


def model_filters(question: str, llm: LLMClient) -> Filters:
    """Ask the model for filters, then keep only the ones the question supports.

    States must be named in the question, or belong to a city that is. Skills must map
    to a known skill named in the question, or else become a keyword the résumé must
    contain. Roles count only when the question uses a role word such as "engineers".
    """
    raw = llm.complete(system=QUERY_SYSTEM, user=question, temperature=0.0, json_mode=True)
    data = parse_json_content(raw)
    rules = rule_filters(question)
    named = set(rules.states)

    cities: dict[str, str] = {}
    for item in data.get("cities") or []:
        if isinstance(item, dict):
            city = str(item.get("city") or "").strip()
            code = state_code(str(item.get("state") or ""))
            if city and code and _in_question(city, question):
                cities[city] = code

    states = _grounded_states(data.get("states"), named, cities)
    exclude = [code for code in _grounded_states(data.get("exclude_states"), named, cities) if code not in states]
    # A state the recruiter named but the model placed in neither list is still a filter.
    states += [code for code in rules.states if code not in states and code not in exclude]

    skills: list[str] = []
    keywords: list[str] = []
    for value in _str_list(data.get("skills")):
        known = [name for name in normalize_skill_list([value]) if find_canonicals(name)]
        if known:
            for name in known:
                if _in_question(value, question) or any(_in_question(alias, question) for alias in aliases_for(name)):
                    skills.append(name)
        elif _in_question(value, question):
            keywords.append(value)

    categories: list[str] = []
    if _ROLE_WORD.search(question):
        for value in _str_list(data.get("roles")):
            categories.extend(categories_for_question(value))
        categories.extend(rules.categories)

    for value in _str_list(data.get("keywords")):
        if _in_question(value, question) and not state_code(value):
            keywords.append(value)

    all_skills = _unique(skills + rules.skills)
    taken = {name.lower() for name in all_skills}
    return Filters(
        skills=all_skills,
        states=_unique(states),
        exclude_states=_unique(exclude),
        categories=_unique(categories),
        keywords=_unique([k for k in keywords if k.lower() not in taken]),
        parser="llm",
    )


def read_filters(question: str, llm: LLMClient | None) -> Filters:
    if llm is not None:
        try:
            return model_filters(question, llm)
        except (LLMError, ValueError, TypeError):
            pass
    return rule_filters(question)


def _skill_clause(skill: str):
    in_profile = cast(Candidate.skills, String).ilike(_like(f'"{skill}"'), escape="\\")
    names = [name for name in aliases_for(skill) if len(name) >= _MIN_TEXT_ALIAS]
    if not names:
        return in_profile
    words = "|".join(re.escape(name) for name in sorted(names, key=len, reverse=True))
    return or_(in_profile, Candidate.redacted_text.op("~*")(rf"(^|[^[:alnum:]])({words})([^[:alnum:]]|$)"))


def _like(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _profile_clauses(filters: Filters) -> list:
    clauses = [_skill_clause(skill) for skill in filters.skills]
    if filters.categories:
        clauses.append(or_(*(cast(Candidate.titles, String).ilike(f"%{label}%") for label in filters.categories)))
    for keyword in filters.keywords:
        clauses.append(Candidate.redacted_text.ilike(_like(keyword), escape="\\"))
    return clauses


@dataclass
class FindResult:
    rows: list[Candidate]
    filters: Filters
    unknown_location: int
    fallback: bool


def find_candidates(session: Session, question: str, llm: LLMClient | None) -> FindResult:
    filters = read_filters(question, llm)
    if filters.empty():
        stmt = select(Candidate)
        if question:
            pattern = _like(question)
            stmt = stmt.where(
                or_(
                    Candidate.full_name.ilike(pattern, escape="\\"),
                    cast(Candidate.skills, String).ilike(pattern, escape="\\"),
                    Candidate.redacted_text.ilike(pattern, escape="\\"),
                )
            )
        rows = session.scalars(stmt.order_by(nullslast(func.lower(Candidate.full_name))).limit(RESULT_LIMIT)).all()
        return FindResult(rows=list(rows), filters=filters, unknown_location=0, fallback=True)

    profile = _profile_clauses(filters)
    stmt = select(Candidate)
    if profile:
        stmt = stmt.where(and_(*profile))
    unknown = 0
    if filters.states or filters.exclude_states:
        unknown_stmt = select(func.count()).select_from(Candidate).where(Candidate.state.is_(None))
        if profile:
            unknown_stmt = unknown_stmt.where(and_(*profile))
        unknown = session.scalar(unknown_stmt) or 0
    if filters.states:
        stmt = stmt.where(Candidate.state.in_(filters.states))
    if filters.exclude_states:
        stmt = stmt.where(Candidate.state.is_not(None), Candidate.state.not_in(filters.exclude_states))
    rows = session.scalars(stmt.order_by(nullslast(func.lower(Candidate.full_name))).limit(RESULT_LIMIT)).all()
    return FindResult(rows=list(rows), filters=filters, unknown_location=unknown, fallback=False)


def describe(result: FindResult) -> str:
    count = len(result.rows)
    people = "person" if count == 1 else "people"
    if result.fallback:
        if not result.rows:
            return "No skill, role, or state was found in that question, and no résumé contains it as written."
        return f"{count} {people} matched that text. No skill, role, or state was found in the question."
    parts: list[str] = []
    if result.filters.categories:
        parts.append("in " + ", ".join(result.filters.categories))
    if result.filters.skills:
        parts.append("with " + " and ".join(result.filters.skills))
    if result.filters.keywords:
        parts.append("mentioning " + " and ".join(f"“{k}”" for k in result.filters.keywords))
    if result.filters.states:
        parts.append("who live in " + " or ".join(state_name(code) for code in result.filters.states))
    if result.filters.exclude_states:
        parts.append("who live outside " + " and ".join(state_name(code) for code in result.filters.exclude_states))
    text = f"{count} {people} " + " ".join(parts) + "."
    if count >= RESULT_LIMIT:
        text += f" Showing the first {RESULT_LIMIT}."
    return text
