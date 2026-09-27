"""Rank open jobs for one confirmed candidate."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.embed import Embedder, cosine
from app.core.llm import LLMClient, LLMError
from app.core.score import MANDATORY_BAR, covers_title, rank_pair, required_coverage, section_coverage
from app.core.tokens import candidate_vector_text, chunk_text
from app.models import Candidate, CandidateChunk, Job, Match


def embed_candidate(session: Session, candidate: Candidate, embedder: Embedder) -> None:
    names = [skill["name"] if isinstance(skill, dict) else str(skill) for skill in (candidate.skills or [])]
    vector_text = candidate_vector_text(candidate.summary or "", list(candidate.titles or []), names)
    vectors = embedder.embed_documents([vector_text])
    candidate.embedding = vectors[0] if vectors else None
    session.query(CandidateChunk).filter(CandidateChunk.candidate_id == candidate.id).delete()
    chunks = chunk_text(candidate.redacted_text or "")
    chunk_vectors = embedder.embed_documents(chunks) if chunks else []
    for index, (text, vector) in enumerate(zip(chunks, chunk_vectors)):
        session.add(
            CandidateChunk(candidate_id=candidate.id, ord=index, text=text, embedding=vector)
        )


def _posting_lines(job: Job, kind: str, names: list[str]) -> list[str]:
    quotes = list((job.skill_quotes or {}).get(kind) or [])
    lines = [line.strip() for line in quotes if isinstance(line, str) and line.strip()]
    if lines:
        return lines
    return [name for name in names if name]


def rank_jobs(
    session: Session,
    candidate: Candidate,
    embedder: Embedder,
    llm: LLMClient,
    required_skills: list[str] | None = None,
) -> list[Match]:
    session.query(Match).filter(Match.candidate_id == candidate.id).delete()
    jobs = session.scalars(select(Job).where(Job.status == "open")).all()
    names = {skill["name"] if isinstance(skill, dict) else str(skill) for skill in (candidate.skills or [])}
    resume_quotes = [chunk.text for chunk in candidate.chunks][:4]
    if not resume_quotes and candidate.redacted_text:
        resume_quotes = chunk_text(candidate.redacted_text)[:4]
    rows: list[Match] = []
    for job in jobs:
        raw = cosine(
            list(candidate.embedding) if candidate.embedding is not None else None,
            list(job.embedding) if job.embedding is not None else None,
        )
        quotes = (job.skill_quotes or {}).get("must") or []
        quotes = list(quotes)[:4]
        if not quotes and job.description_text:
            quotes = [part.strip() for part in job.description_text.split("\n\n") if part.strip()][:4]
        must_lines = _posting_lines(job, "must", list(job.must_have_skills or []))
        nice_lines = _posting_lines(job, "nice", list(job.nice_to_have_skills or []))
        mandatory = section_coverage(names, must_lines, candidate.redacted_text or "")
        desired = section_coverage(names, nice_lines, candidate.redacted_text or "")
        if not covers_title(names, job.title):
            mandatory = {**mandatory, "pct": 0.0, "hit": 0, "matched": []}
        required = required_coverage(names, must_lines, required_skills or [])
        mandatory_pct = mandatory["pct"]
        meets_bar = mandatory_pct is not None and mandatory_pct >= MANDATORY_BAR and not required["missing"]
        scored = rank_pair(
            names,
            set(job.must_have_skills or []),
            set(job.nice_to_have_skills or []),
            raw,
            description_on_file=bool((job.description_text or "").strip()),
            candidate_clearance=candidate.clearance,
            candidate_poly=candidate.polygraph,
            job_clearance=job.clearance_required,
            job_poly=job.polygraph_required,
        )
        explanation = None
        try:
            explanation = llm.complete(
                system=(
                    "Explain in 2 to 4 sentences why this candidate fits this open job. "
                    "Use only the overlapping skills and the quotes. Do not add skills that are absent."
                ),
                user=(
                    f"job {job.requisition_code} {job.title} {job.location}\n"
                    f"overlap {scored['overlap_skills']}\n"
                    f"job quotes {quotes}\n"
                    f"resume quotes {resume_quotes}"
                ),
                temperature=0.2,
                json_mode=False,
            )
        except LLMError:
            explanation = None
        row = Match(
            candidate_id=candidate.id,
            job_id=job.id,
            skill_score=scored["skill_score"],
            raw_cosine=scored["raw_cosine"],
            semantic=scored["semantic"],
            final=scored["final"],
            confidence=scored["confidence"],
            overlap_skills=scored["overlap_skills"],
            clearance_flag=scored["clearance_flag"],
            job_quotes=quotes,
            resume_quotes=resume_quotes,
            explanation=explanation,
        )
        row.mandatory_pct = mandatory_pct
        row.mandatory_hit = mandatory["hit"]
        row.mandatory_total = mandatory["total"]
        row.mandatory_matched = mandatory["matched"]
        row.desired_pct = desired["pct"]
        row.desired_hit = desired["hit"]
        row.desired_total = desired["total"]
        row.desired_matched = desired["matched"]
        row.desired_any = desired["hit"] > 0
        row.required_pct = required["pct"]
        row.required_matched = required["matched"]
        row.required_missing = required["missing"]
        row.meets_bar = meets_bar
        session.add(row)
        rows.append(row)
    rows.sort(
        key=lambda item: (
            1 if item.meets_bar else 0,
            item.mandatory_pct if item.mandatory_pct is not None else -1,
            1 if item.desired_any else 0,
            item.desired_pct if item.desired_pct is not None else -1,
            item.final or 0,
        ),
        reverse=True,
    )
    return rows
