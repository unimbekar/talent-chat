"""Assistant chat (server-sent events) and the quick search behind Ctrl+K."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from app.admin.assistant.engine import run_turn
from app.admin.routes import _person_name, require_admin
from app.config import get_settings
from app.core.llm import build_llm_client
from app.db import admin_session
from app.models import Candidate, Job, Submission

router = APIRouter(prefix="/admin", tags=["assistant"])
logger = logging.getLogger(__name__)

QUICK_JOBS = 6
QUICK_CANDIDATES = 8
QUICK_SUBMISSIONS = 5


class ChatMessage(BaseModel):
    role: str
    content: str = Field(default="", max_length=8000)
    # Tool steps behind an earlier assistant reply: {"tool", "args", "summary"}.
    tools: list[dict] = Field(default_factory=list, max_length=12)


class AssistantIn(BaseModel):
    messages: list[ChatMessage] = Field(default_factory=list, max_length=40)
    page: dict = Field(default_factory=dict)
    timezone: str = "UTC"


def _assistant_model() -> tuple[str, str]:
    settings = get_settings()
    backend = settings.assistant_backend.strip() or settings.llm_backend
    model = settings.assistant_model.strip() or settings.llm_model
    return backend, model


def assistant_llm(request: Request):
    """The app's LLM, or a separate client when ASSISTANT_BACKEND or ASSISTANT_MODEL is set."""
    settings = get_settings()
    if not (settings.assistant_backend.strip() or settings.assistant_model.strip()):
        return request.app.state.llm
    client = getattr(request.app.state, "assistant_llm", None)
    if client is None:
        backend, model = _assistant_model()
        client = build_llm_client(backend, settings.llm_base_url, model, settings.llm_api_key, settings.aws_region)
        request.app.state.assistant_llm = client
    return client


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, default=str, ensure_ascii=False)}\n\n"


@router.get("/assistant/info")
def assistant_info(session: Session = Depends(require_admin)):
    del session
    backend, model = _assistant_model()
    return {"backend": backend, "model": model}


@router.post("/assistant")
def assistant(body: AssistantIn, request: Request, session: Session = Depends(require_admin)):
    # The dependency session only proves the sign-in. The stream outlives it, so it opens its own.
    del session
    llm = assistant_llm(request)
    embedder = getattr(request.app.state, "embedder", None)
    settings = get_settings()
    _backend, model = _assistant_model()
    messages = [message.model_dump() for message in body.messages]

    def stream():
        db = admin_session()
        try:
            yield ": open\n\n"
            for event in run_turn(
                session=db,
                llm=llm,
                embedder=embedder,
                messages=messages,
                page=body.page,
                timezone_name=body.timezone,
                max_steps=settings.assistant_max_steps,
                model_name=model,
            ):
                yield _sse(event)
        except Exception:
            logger.exception("assistant turn failed")
            yield _sse({"type": "error", "message": "The assistant hit an unexpected error. Try again."})
        finally:
            db.close()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


def _like(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


@router.get("/search")
def quick_search(q: str = "", session: Session = Depends(require_admin)):
    """Instant lookup across jobs, candidates, and submissions. Every word has to match."""
    words = [word for word in q.strip().split() if word][:6]
    if not words or len(q.strip()) < 2:
        return {"q": q, "jobs": [], "candidates": [], "submissions": []}

    job_stmt = select(Job)
    for word in words:
        pattern = _like(word)
        job_stmt = job_stmt.where(
            or_(
                Job.requisition_code.ilike(pattern, escape="\\"),
                Job.title.ilike(pattern, escape="\\"),
                Job.location.ilike(pattern, escape="\\"),
                cast(Job.must_have_skills, String).ilike(pattern, escape="\\"),
            )
        )
    jobs = session.scalars(
        job_stmt.order_by((Job.status == "closed").asc(), Job.requisition_code).limit(QUICK_JOBS)
    ).all()

    cand_stmt = select(Candidate)
    for word in words:
        pattern = _like(word)
        cand_stmt = cand_stmt.where(
            or_(
                Candidate.full_name.ilike(pattern, escape="\\"),
                Candidate.email.ilike(pattern, escape="\\"),
                Candidate.original_filename.ilike(pattern, escape="\\"),
                Candidate.location.ilike(pattern, escape="\\"),
                cast(Candidate.skills, String).ilike(pattern, escape="\\"),
                cast(Candidate.titles, String).ilike(pattern, escape="\\"),
            )
        )
    candidates = session.scalars(cand_stmt.order_by(func.lower(Candidate.full_name)).limit(QUICK_CANDIDATES)).all()

    sub_stmt = (
        select(Submission)
        .join(Candidate, Submission.candidate_id == Candidate.id)
        .join(Job, Submission.job_id == Job.id)
    )
    for word in words:
        pattern = _like(word)
        sub_stmt = sub_stmt.where(
            or_(
                Candidate.full_name.ilike(pattern, escape="\\"),
                Candidate.email.ilike(pattern, escape="\\"),
                Job.requisition_code.ilike(pattern, escape="\\"),
                Job.title.ilike(pattern, escape="\\"),
                Submission.stage.ilike(pattern, escape="\\"),
            )
        )
    submissions = session.scalars(sub_stmt.order_by(Submission.updated_at.desc()).limit(QUICK_SUBMISSIONS)).all()

    return {
        "q": q,
        "jobs": [
            {
                "code": job.requisition_code,
                "title": job.title,
                "location": job.location,
                "status": job.status,
                "href": f"/admin/jobs/{job.requisition_code}",
            }
            for job in jobs
        ],
        "candidates": [
            {
                "id": str(row.id),
                "name": _person_name(row) or row.original_filename,
                "email": row.email,
                "location": row.location,
                "title": (row.titles or [None])[0],
                "href": f"/admin/candidates/{row.id}",
            }
            for row in candidates
        ],
        "submissions": [
            {
                "id": str(row.id),
                "candidate": row.candidate.full_name or row.candidate.original_filename,
                "code": row.job.requisition_code,
                "title": row.job.title,
                "stage": row.stage,
                "href": f"/admin/submissions/{row.id}",
            }
            for row in submissions
        ],
    }
