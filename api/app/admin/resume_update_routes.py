"""Save justifications for missing requirements and download a résumé that includes them."""

from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin.access import actor_of, require_desk
from app.admin.resume_docx import build_updated_resume, clean_justification, download_name, justification_error
from app.admin.routes import _audit, _review_one
from app.models import Candidate, Job, ResumeUpdate

router = APIRouter(prefix="/admin", tags=["admin"])


class JustificationIn(BaseModel):
    line: str
    justification: str = ""


class ResumeUpdateIn(BaseModel):
    requisition_code: str
    candidate_id: uuid.UUID
    items: list[JustificationIn] = Field(default_factory=list)


def _load(session: Session, code: str, candidate_id: uuid.UUID) -> tuple[Job, Candidate, dict]:
    job = session.scalar(select(Job).where(Job.requisition_code == code))
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    candidate = session.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    return job, candidate, _review_one(job, candidate)


def _missing(review: dict) -> list[tuple[str, str]]:
    rows = [("Mandatory", line) for line in review.get("mandatory_missing") or []]
    rows.extend(("Desired", line) for line in review.get("desired_missing") or [])
    return [(line, kind) for kind, line in rows]


def _stored_map(row: ResumeUpdate | None) -> dict[str, str]:
    if row is None:
        return {}
    found = {}
    for item in row.items or []:
        if isinstance(item, dict) and item.get("line"):
            found[str(item["line"])] = str(item.get("justification") or "")
    return found


def _view(job: Job, candidate: Candidate, review: dict, row: ResumeUpdate | None) -> dict:
    saved = _stored_map(row)
    missing = []
    for line, kind in _missing(review):
        text = saved.get(line, "")
        missing.append({"line": line, "kind": kind, "justification": text, "ready": justification_error(text) is None and bool(text)})
    return {
        "job": review["job"],
        "candidate": review["candidate"],
        "missing": missing,
        "complete": bool(missing) and all(item["ready"] for item in missing),
        "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
        "updated_by": row.updated_by if row else "",
        "has_file": bool(candidate.original_path),
    }


def _accept(missing: list[tuple[str, str]], items: list[JustificationIn]) -> list[dict]:
    allowed = {line: kind for line, kind in missing}
    kept: dict[str, dict] = {}
    for item in items:
        line = item.line.strip()
        if line not in allowed:
            raise HTTPException(status_code=400, detail="That requirement is not missing on this résumé.")
        text = clean_justification(item.justification)
        if not text:
            continue
        problem = justification_error(text)
        if problem:
            raise HTTPException(status_code=400, detail=f"{problem} ({line})")
        kept[line] = {"line": line, "kind": allowed[line], "justification": text}
    return [kept[line] for line, _kind in missing if line in kept]


@router.get("/resume-update")
def read_resume_update(code: str, candidate_id: uuid.UUID, session: Session = Depends(require_desk)):
    job, candidate, review = _load(session, code, candidate_id)
    row = session.scalar(select(ResumeUpdate).where(ResumeUpdate.candidate_id == candidate.id, ResumeUpdate.job_id == job.id))
    return _view(job, candidate, review, row)


@router.put("/resume-update")
def save_resume_update(body: ResumeUpdateIn, session: Session = Depends(require_desk)):
    job, candidate, review = _load(session, body.requisition_code.strip(), body.candidate_id)
    items = _accept(_missing(review), body.items)
    row = session.scalar(select(ResumeUpdate).where(ResumeUpdate.candidate_id == candidate.id, ResumeUpdate.job_id == job.id))
    if row is None:
        row = ResumeUpdate(candidate_id=candidate.id, job_id=job.id)
        session.add(row)
    row.items = items
    row.updated_by = actor_of(session)
    row.updated_at = datetime.now(timezone.utc)
    _audit(session, "resume_update", candidate.id, job.requisition_code)
    session.commit()
    session.refresh(row)
    return _view(job, candidate, review, row)


@router.get("/resume-update/file")
def download_resume_update(code: str, candidate_id: uuid.UUID, session: Session = Depends(require_desk)):
    job, candidate, review = _load(session, code, candidate_id)
    missing = _missing(review)
    if not missing:
        raise HTTPException(status_code=400, detail="This résumé already covers the listed requirements. Download the original file.")
    row = session.scalar(select(ResumeUpdate).where(ResumeUpdate.candidate_id == candidate.id, ResumeUpdate.job_id == job.id))
    saved = _stored_map(row)
    ready = []
    gaps = []
    for line, kind in missing:
        text = saved.get(line, "")
        if text and justification_error(text) is None:
            ready.append({"line": line, "kind": kind, "justification": text})
        else:
            gaps.append(line)
    if gaps:
        raise HTTPException(status_code=400, detail="Add a justification for every missing requirement before downloading.")
    name = review["candidate"].get("full_name") or "Résumé"
    payload = build_updated_resume(
        name=name,
        code=job.requisition_code,
        title=job.title,
        filename=candidate.original_filename,
        author=row.updated_by if row else actor_of(session),
        items=ready,
        resume_text=candidate.redacted_text or "",
    )
    filename = download_name(name, job.requisition_code)
    _audit(session, "resume_update_download", candidate.id, job.requisition_code)
    session.commit()
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
