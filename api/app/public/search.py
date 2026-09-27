"""Public job search. Uses the caller's session, which must be the app_public role."""

from dataclasses import dataclass, field
import re

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.embed import Embedder, cosine
from app.core.locations import load_locations, load_places, miles_from_place
from app.core.tokens import query_vector_text
from app.models import Job, SkillSynonym
from app.public.query import ParsedQuery, parse_query

_CODE = re.compile(r"\b[A-Z][0-9]{3,5}\b")


@dataclass
class SearchHit:
    job: Job
    matched_skills: list[str]
    distance_miles: float | None = None
    near_place: str | None = None


@dataclass
class SearchResult:
    hits: list[SearchHit] = field(default_factory=list)
    no_jobs_loaded: bool = False
    parsed: ParsedQuery | None = None


def load_synonyms(session: Session) -> list[tuple[str, str]]:
    rows = session.execute(select(SkillSynonym.alias, SkillSynonym.canonical)).all()
    return [(alias, canonical) for alias, canonical in rows]


def search_jobs(
    session: Session,
    message: str,
    prior_codes: list[str] | None = None,
    embedder: Embedder | None = None,
) -> SearchResult:
    total = session.scalar(select(func.count()).select_from(Job)) or 0
    if total == 0:
        return SearchResult(no_jobs_loaded=True)
    synonyms = load_synonyms(session)
    locations = load_locations()
    parsed = parse_query(message, synonyms, locations, prior_codes)
    if parsed.codes and not parsed.skills and not parsed.city and not parsed.exclude_city and not parsed.prior_only:
        jobs = session.scalars(
            select(Job).where(Job.status == "open", Job.requisition_code.in_(parsed.codes))
        ).all()
        hits = [SearchHit(job=job, matched_skills=[]) for job in jobs]
        return SearchResult(hits=hits, parsed=parsed)

    # "Show me all positions" has no skill, city, or keyword. List every open job.
    # Do not rerank that list with the embedding of the question itself.
    if not parsed.skills and not parsed.city and not parsed.exclude_city and not parsed.fts and not parsed.prior_only:
        jobs = session.scalars(select(Job).where(Job.status == "open").order_by(Job.requisition_code)).all()
        return SearchResult(hits=[SearchHit(job=job, matched_skills=[]) for job in jobs], parsed=parsed)

    stmt = select(Job).where(Job.status == "open")
    if parsed.prior_only:
        stmt = stmt.where(Job.requisition_code.in_(prior_codes or []))
    if parsed.exclude_city and not parsed.prior_only:
        stmt = stmt.where(Job.location != parsed.exclude_city)
    elif parsed.city and not parsed.prior_only:
        stmt = stmt.where(Job.location == parsed.city)
    if parsed.senior_only and parsed.prior_only:
        stmt = stmt.where(Job.title.ilike("%senior%"))
    # A follow-up keeps the jobs already on screen. Skill words in the
    # question are for the model to answer, not a new filter on that set.
    if not parsed.prior_only:
        for skill, aliases in parsed.skill_aliases.items():
            conditions = [
                Job.must_have_skills.overlap([skill]),
                Job.nice_to_have_skills.overlap([skill]),
            ]
            for alias in aliases:
                pattern = _pg_boundary(alias)
                conditions.append(Job.description_text.op("~*")(pattern))
                conditions.append(Job.title.op("~*")(pattern))
            stmt = stmt.where(or_(*conditions))
    if parsed.fts and not parsed.prior_only and not (parsed.exclude_city and not parsed.skills):
        stmt = stmt.where(Job.tsv.op("@@")(func.plainto_tsquery("english", parsed.fts)))
    jobs = list(session.scalars(stmt).all())
    distances: dict[str, float] = {}
    if parsed.near_place:
        origin = next((place for place in load_places() if place.name == parsed.near_place), None)
        kept = []
        for job in jobs:
            miles = miles_from_place(origin, job.location, locations) if origin is not None else None
            if miles is None:
                continue
            if parsed.near_miles is not None and miles > parsed.near_miles:
                continue
            distances[job.requisition_code] = miles
            kept.append(job)
        jobs = kept
    exclude_only = bool(parsed.exclude_city and not parsed.skills and not parsed.prior_only)
    if parsed.near_place:
        jobs.sort(key=lambda job: (distances.get(job.requisition_code, 1e9), job.requisition_code))
    elif exclude_only:
        jobs.sort(key=lambda job: (job.location or "", job.requisition_code))
    elif embedder is not None and jobs and any(job.embedding is not None for job in jobs):
        try:
            query_vector = embedder.embed_query(query_vector_text(message))
            jobs.sort(
                key=lambda job: cosine(list(job.embedding) if job.embedding is not None else None, query_vector),
                reverse=True,
            )
        except Exception:
            pass
    wants_all = bool(parsed.skills and re.search(r"(?i)\ball\b", message))
    limit = 24 if exclude_only or parsed.near_place or wants_all else 8
    hits = []
    for job in jobs[:limit]:
        job_skills = set(job.must_have_skills or []) | set(job.nice_to_have_skills or [])
        matched = [skill for skill in parsed.skills if skill in job_skills or _text_has(job, parsed.skill_aliases.get(skill, []))]
        hits.append(
            SearchHit(
                job=job,
                matched_skills=matched or list(parsed.skills),
                distance_miles=distances.get(job.requisition_code),
                near_place=parsed.near_place if job.requisition_code in distances else None,
            )
        )
    return SearchResult(hits=hits, parsed=parsed)


def drop_unknown_codes(text: str, allowed: set[str]) -> str:
    def replace(match: re.Match[str]) -> str:
        code = match.group(0)
        return code if code in allowed else ""

    cleaned = _CODE.sub(replace, text or "")
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def _text_has(job: Job, aliases: list[str]) -> bool:
    blob = f"{job.title or ''}\n{job.description_text or ''}"
    return any(re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", blob, re.I) for alias in aliases)


def _pg_boundary(alias: str) -> str:
    escaped = re.escape(alias)
    return rf"\y{escaped}\y"
