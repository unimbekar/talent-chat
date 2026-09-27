"""Candidate persistence. Public code must not import this module."""

from pathlib import Path
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Candidate, CandidateChunk, Match


def by_hash(session: Session, digest: str) -> Candidate | None:
    return session.scalar(select(Candidate).where(Candidate.file_sha256 == digest))


def get_candidate(session: Session, candidate_id: uuid.UUID) -> Candidate | None:
    return session.get(Candidate, candidate_id)


def delete_candidate(session: Session, candidate: Candidate) -> None:
    if candidate.original_path:
        path = Path(candidate.original_path)
        if path.exists():
            path.unlink()
    session.query(Match).filter(Match.candidate_id == candidate.id).delete()
    session.query(CandidateChunk).filter(CandidateChunk.candidate_id == candidate.id).delete()
    session.delete(candidate)
