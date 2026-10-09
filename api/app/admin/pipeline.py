"""Recruiter submission pipeline.

A submission is one candidate sent for one job. The row is kept after it ends,
so a candidate page can show every job that person was submitted for. Stage
changes and salary changes are appended to submission_events and are not edited.
Comments on a submission, and notes on the person, can be edited or removed.
"""

from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.admin.auth import cookie_name, read_session
from app.db import get_admin_db
from app.models import (
    AuditLog,
    Candidate,
    CandidateComment,
    Job,
    Submission,
    SubmissionComment,
    SubmissionEvent,
)

router = APIRouter(prefix="/admin", tags=["pipeline"])

SALARY_MAX = 5_000_000


class Stage:
    def __init__(self, key: str, label: str, terminal: bool, detail: str) -> None:
        self.key = key
        self.label = label
        self.terminal = terminal
        self.detail = detail

    def as_dict(self, count: int | None = None) -> dict:
        payload = {"key": self.key, "label": self.label, "terminal": self.terminal, "detail": self.detail}
        if count is not None:
            payload["count"] = count
        return payload


# The main path is ordered. Selected, rejected, and withdrawn end the submission.
STAGES: tuple[Stage, ...] = (
    Stage("submitted", "Submitted", False, "The résumé was sent for this job."),
    Stage("salary", "Salary", False, "Compensation for this job is on record."),
    Stage("interviewed", "Interviewed", False, "The candidate has interviewed."),
    Stage("offer", "Offer", False, "An offer is in front of the candidate."),
    Stage("selected", "Selected", True, "The client selected this candidate."),
    Stage("rejected", "Rejected", True, "The submission did not move forward."),
    Stage("withdrawn", "Withdrawn", True, "The candidate or the firm pulled the submission."),
)
STAGE_BY_KEY = {stage.key: stage for stage in STAGES}
FLOW = [stage.key for stage in STAGES if not stage.terminal or stage.key == "selected"]
EXITS = [stage.key for stage in STAGES if stage.terminal and stage.key != "selected"]
# Selected stays on the working board. Rejected and withdrawn are history.
CLOSED_STAGES = frozenset(EXITS)


def require_admin(request: Request, session: Session = Depends(get_admin_db)) -> Session:
    token = request.cookies.get(cookie_name())
    if read_session(session, token) is None:
        raise HTTPException(status_code=401, detail="Sign in required.")
    return session


class SubmissionIn(BaseModel):
    candidate_id: uuid.UUID
    requisition_code: str
    stage: str = "submitted"
    salary_usd: int | None = None
    salary_note: str | None = None
    note: str | None = None


class SubmissionPatch(BaseModel):
    stage: str | None = None
    salary_usd: int | None = None
    salary_note: str | None = None
    note: str | None = None


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(session: Session, action: str, subject_id: uuid.UUID | None, outcome: str | None = None) -> None:
    session.add(AuditLog(actor="admin", action=action, subject_id=subject_id, outcome=outcome))


def _fail(status: int, message: str, **extra) -> None:
    raise HTTPException(status_code=status, detail={"message": message, **extra})


def _stage(key: str) -> Stage:
    stage = STAGE_BY_KEY.get(key)
    if stage is None:
        known = ", ".join(item.key for item in STAGES)
        _fail(400, f"Stage must be one of: {known}.")
    return stage


def _salary(amount: int | None) -> int | None:
    if amount is None:
        return None
    if amount < 1 or amount > SALARY_MAX:
        _fail(400, "Salary must be between 1 and 5,000,000 dollars a year.")
    return amount


def _note(value: str | None, limit: int = 2000) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    if len(text) > limit:
        _fail(400, f"Keep that note under {limit} characters.")
    return text


def _comment_body(value: str) -> str:
    text = value.strip()
    if not text:
        _fail(400, "Write a comment before saving.")
    if len(text) > 4000:
        _fail(400, "Keep a comment under 4,000 characters.")
    return text


def _person(candidate: Candidate) -> str:
    return (candidate.full_name or candidate.original_filename or "This candidate").strip()


def _job_brief(job: Job) -> dict:
    return {
        "requisition_code": job.requisition_code,
        "title": job.title,
        "location": job.location,
        "status": job.status,
    }


def _candidate_brief(candidate: Candidate) -> dict:
    return {
        "id": str(candidate.id),
        "full_name": candidate.full_name,
        "email": candidate.email,
        "location": candidate.location,
        "original_filename": candidate.original_filename,
    }


def _comment_out(row: SubmissionComment | CandidateComment) -> dict:
    return {
        "id": str(row.id),
        "body": row.body,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "edited": bool(row.updated_at and row.created_at and row.updated_at > row.created_at),
    }


def _event_out(row: SubmissionEvent) -> dict:
    return {
        "id": str(row.id),
        "kind": row.kind,
        "from_stage": row.from_stage,
        "to_stage": row.to_stage,
        "from_label": None if row.from_stage is None else STAGE_BY_KEY[row.from_stage].label if row.from_stage in STAGE_BY_KEY else row.from_stage,
        "to_label": None if row.to_stage is None else STAGE_BY_KEY[row.to_stage].label if row.to_stage in STAGE_BY_KEY else row.to_stage,
        "body": row.body,
        "salary_usd": row.salary_usd,
        "at": row.at.isoformat() if row.at else None,
    }


def _card(row: Submission, comment_count: int | None = None) -> dict:
    stage = STAGE_BY_KEY.get(row.stage)
    count = comment_count
    if count is None:
        count = len(row.comments or [])
    return {
        "id": str(row.id),
        "stage": row.stage,
        "stage_label": stage.label if stage else row.stage,
        "terminal": bool(stage and stage.terminal),
        "salary_usd": row.salary_usd,
        "salary_note": row.salary_note,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "comment_count": count,
        "candidate": _candidate_brief(row.candidate),
        "job": _job_brief(row.job),
    }


def _application_out(row: Submission) -> dict | None:
    application = row.application
    if application is None:
        return None
    return {
        "full_name": application.full_name,
        "email": application.email,
        "phone": application.phone,
        "location": application.location,
        "salary_usd": application.salary_usd,
        "start_on": application.start_on.isoformat() if application.start_on else None,
        "years_experience": application.years_experience,
        "fsp": application.fsp,
        "last_fsp_on": application.last_fsp_on.isoformat() if application.last_fsp_on else None,
        "last_tssci_on": application.last_tssci_on.isoformat() if application.last_tssci_on else None,
        "note": application.note,
        "created_at": application.created_at.isoformat() if application.created_at else None,
    }


def _detail(row: Submission) -> dict:
    payload = _card(row)
    payload["events"] = [_event_out(event) for event in row.events]
    payload["comments"] = [_comment_out(comment) for comment in reversed(list(row.comments))]
    payload["application"] = _application_out(row)
    payload["flow"] = FLOW
    payload["exits"] = EXITS
    return payload


def _load(session: Session, submission_id: uuid.UUID) -> Submission:
    row = session.get(Submission, submission_id)
    if row is None or row.candidate is None or row.job is None:
        _fail(404, "That submission is not on file.")
    return row


def _event(
    session: Session,
    row: Submission,
    kind: str,
    *,
    from_stage: str | None,
    to_stage: str | None,
    body: str | None,
) -> None:
    session.add(
        SubmissionEvent(
            submission_id=row.id,
            kind=kind,
            from_stage=from_stage,
            to_stage=to_stage,
            body=body,
            salary_usd=row.salary_usd,
            at=_now(),
        )
    )


def create_submission(session: Session, body: SubmissionIn) -> Submission:
    stage = _stage(body.stage)
    salary = _salary(body.salary_usd)
    note = _note(body.note)
    salary_note = _note(body.salary_note, 500)
    candidate = session.get(Candidate, body.candidate_id)
    if candidate is None:
        _fail(404, "That candidate is not on file.")
    code = body.requisition_code.strip()
    job = session.scalar(select(Job).where(Job.requisition_code == code))
    if job is None:
        _fail(404, f"No job with code {code}.")
    existing = session.scalar(
        select(Submission).where(Submission.candidate_id == candidate.id, Submission.job_id == job.id)
    )
    if existing is not None:
        _fail(
            409,
            f"{_person(candidate)} is already submitted for {job.requisition_code}.",
            submission_id=str(existing.id),
        )
    now = _now()
    row = Submission(
        candidate_id=candidate.id,
        job_id=job.id,
        stage=stage.key,
        salary_usd=salary,
        salary_note=salary_note,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.flush()
    _event(session, row, "created", from_stage=None, to_stage=stage.key, body=note)
    _audit(session, "submission_create", row.id, stage.key)
    session.commit()
    session.refresh(row)
    return row


def update_submission(session: Session, submission_id: uuid.UUID, body: SubmissionPatch) -> Submission:
    row = _load(session, submission_id)
    sent = body.model_fields_set
    if not sent:
        _fail(400, "Nothing to change.")
    note = _note(body.note) if "note" in sent else None
    stage_changed = False
    salary_changed = False
    previous = row.stage
    if "stage" in sent and body.stage is not None and body.stage != row.stage:
        row.stage = _stage(body.stage).key
        stage_changed = True
    elif "stage" in sent and body.stage is not None:
        _stage(body.stage)
    if "salary_usd" in sent:
        amount = _salary(body.salary_usd)
        if amount != row.salary_usd:
            row.salary_usd = amount
            salary_changed = True
    if "salary_note" in sent:
        text = _note(body.salary_note, 500)
        if text != row.salary_note:
            row.salary_note = text
            salary_changed = True
    if not stage_changed and not salary_changed:
        if note:
            _fail(400, "Add that as a comment. A note here is saved with a stage or salary change.")
        _fail(400, "That is already the current stage and salary.")
    row.updated_at = _now()
    if stage_changed:
        _event(session, row, "stage", from_stage=previous, to_stage=row.stage, body=note)
        _audit(session, "submission_stage", row.id, f"{previous}->{row.stage}")
    elif salary_changed or note is not None:
        _event(session, row, "salary", from_stage=row.stage, to_stage=row.stage, body=note)
        _audit(session, "submission_salary", row.id, None if row.salary_usd is None else str(row.salary_usd))
    session.commit()
    session.refresh(row)
    return row


def delete_submission(session: Session, submission_id: uuid.UUID) -> None:
    row = _load(session, submission_id)
    _audit(session, "submission_delete", row.id, row.stage)
    session.delete(row)
    session.commit()


def list_submissions(
    session: Session,
    *,
    stage: str | None,
    scope: str,
    code: str | None,
    candidate_id: uuid.UUID | None,
    q: str,
) -> list[Submission]:
    if stage:
        _stage(stage)
    if scope not in {"active", "all", "closed"}:
        _fail(400, "Scope must be active, all, or closed.")
    stmt = select(Submission).join(Candidate, Submission.candidate_id == Candidate.id).join(Job, Submission.job_id == Job.id)
    if stage:
        stmt = stmt.where(Submission.stage == stage)
    elif scope == "active":
        stmt = stmt.where(Submission.stage.notin_(CLOSED_STAGES))
    elif scope == "closed":
        stmt = stmt.where(Submission.stage.in_(CLOSED_STAGES))
    if code:
        stmt = stmt.where(Job.requisition_code == code.strip())
    if candidate_id is not None:
        stmt = stmt.where(Submission.candidate_id == candidate_id)
    term = q.strip()
    if term:
        pattern = f"%{term.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')}%"
        stmt = stmt.where(
            or_(
                Candidate.full_name.ilike(pattern, escape="\\"),
                Candidate.email.ilike(pattern, escape="\\"),
                Job.requisition_code.ilike(pattern, escape="\\"),
                Job.title.ilike(pattern, escape="\\"),
            )
        )
    return list(session.scalars(stmt.order_by(Submission.updated_at.desc(), Submission.created_at.desc())).all())


def counts_by_stage(session: Session) -> dict[str, int]:
    rows = session.execute(select(Submission.stage, func.count()).group_by(Submission.stage)).all()
    return {stage: total for stage, total in rows}


def counts_by_job(session: Session) -> dict[uuid.UUID, int]:
    rows = session.execute(select(Submission.job_id, func.count()).group_by(Submission.job_id)).all()
    return {job_id: total for job_id, total in rows}


def add_submission_comment(session: Session, submission_id: uuid.UUID, body: str) -> SubmissionComment:
    row = _load(session, submission_id)
    text = _comment_body(body)
    now = _now()
    comment = SubmissionComment(submission_id=row.id, body=text, created_at=now, updated_at=now)
    session.add(comment)
    _audit(session, "submission_comment", row.id, "create")
    session.commit()
    session.refresh(comment)
    return comment


def edit_submission_comment(session: Session, submission_id: uuid.UUID, comment_id: uuid.UUID, body: str) -> SubmissionComment:
    _load(session, submission_id)
    comment = session.get(SubmissionComment, comment_id)
    if comment is None or comment.submission_id != submission_id:
        _fail(404, "That comment is not on this submission.")
    comment.body = _comment_body(body)
    comment.updated_at = _now()
    _audit(session, "submission_comment", submission_id, "edit")
    session.commit()
    session.refresh(comment)
    return comment


def remove_submission_comment(session: Session, submission_id: uuid.UUID, comment_id: uuid.UUID) -> None:
    _load(session, submission_id)
    comment = session.get(SubmissionComment, comment_id)
    if comment is None or comment.submission_id != submission_id:
        _fail(404, "That comment is not on this submission.")
    session.delete(comment)
    _audit(session, "submission_comment", submission_id, "delete")
    session.commit()


def list_candidate_comments(session: Session, candidate_id: uuid.UUID) -> list[CandidateComment]:
    if session.get(Candidate, candidate_id) is None:
        _fail(404, "That candidate is not on file.")
    return list(
        session.scalars(
            select(CandidateComment)
            .where(CandidateComment.candidate_id == candidate_id)
            .order_by(CandidateComment.created_at.desc())
        ).all()
    )


def add_candidate_comment(session: Session, candidate_id: uuid.UUID, body: str) -> CandidateComment:
    if session.get(Candidate, candidate_id) is None:
        _fail(404, "That candidate is not on file.")
    now = _now()
    comment = CandidateComment(candidate_id=candidate_id, body=_comment_body(body), created_at=now, updated_at=now)
    session.add(comment)
    _audit(session, "candidate_comment", candidate_id, "create")
    session.commit()
    session.refresh(comment)
    return comment


def edit_candidate_comment(session: Session, candidate_id: uuid.UUID, comment_id: uuid.UUID, body: str) -> CandidateComment:
    comment = session.get(CandidateComment, comment_id)
    if comment is None or comment.candidate_id != candidate_id:
        _fail(404, "That comment is not on this candidate.")
    comment.body = _comment_body(body)
    comment.updated_at = _now()
    _audit(session, "candidate_comment", candidate_id, "edit")
    session.commit()
    session.refresh(comment)
    return comment


def remove_candidate_comment(session: Session, candidate_id: uuid.UUID, comment_id: uuid.UUID) -> None:
    comment = session.get(CandidateComment, comment_id)
    if comment is None or comment.candidate_id != candidate_id:
        _fail(404, "That comment is not on this candidate.")
    session.delete(comment)
    _audit(session, "candidate_comment", candidate_id, "delete")
    session.commit()


def _pipeline_payload(session: Session, rows: list[Submission]) -> dict:
    counts = counts_by_stage(session)
    active = sum(total for key, total in counts.items() if key not in CLOSED_STAGES)
    return {
        "stages": [stage.as_dict(counts.get(stage.key, 0)) for stage in STAGES],
        "flow": FLOW,
        "exits": EXITS,
        "active": active,
        "total": sum(counts.values()),
        "submissions": [_card(row) for row in rows],
    }


@router.get("/pipeline")
def pipeline(
    session: Session = Depends(require_admin),
    stage: str = "",
    scope: str = "active",
    code: str = "",
    candidate_id: uuid.UUID | None = None,
    q: str = "",
):
    rows = list_submissions(
        session,
        stage=stage or None,
        scope=scope,
        code=code or None,
        candidate_id=candidate_id,
        q=q,
    )
    return _pipeline_payload(session, rows)


@router.get("/pipeline/stages")
def pipeline_stages(session: Session = Depends(require_admin)):
    counts = counts_by_stage(session)
    return {"stages": [stage.as_dict(counts.get(stage.key, 0)) for stage in STAGES], "flow": FLOW, "exits": EXITS}


@router.post("/submissions")
def post_submission(body: SubmissionIn, session: Session = Depends(require_admin)):
    return _detail(create_submission(session, body))


@router.get("/submissions/{submission_id}")
def get_submission(submission_id: uuid.UUID, session: Session = Depends(require_admin)):
    return _detail(_load(session, submission_id))


@router.patch("/submissions/{submission_id}")
def patch_submission(submission_id: uuid.UUID, body: SubmissionPatch, session: Session = Depends(require_admin)):
    return _detail(update_submission(session, submission_id, body))


@router.delete("/submissions/{submission_id}")
def remove_submission(submission_id: uuid.UUID, session: Session = Depends(require_admin)):
    delete_submission(session, submission_id)
    return {"ok": True}


@router.get("/jobs/{code}/submissions")
def job_submissions(code: str, session: Session = Depends(require_admin)):
    job = session.scalar(select(Job).where(Job.requisition_code == code))
    if job is None:
        _fail(404, "Job not found.")
    rows = list_submissions(session, stage=None, scope="all", code=code, candidate_id=None, q="")
    return {"job": _job_brief(job), "submissions": [_card(row) for row in rows]}


@router.get("/resumes/{candidate_id}/submissions")
def candidate_submissions(candidate_id: uuid.UUID, session: Session = Depends(require_admin)):
    candidate = session.get(Candidate, candidate_id)
    if candidate is None:
        _fail(404, "That candidate is not on file.")
    rows = list_submissions(session, stage=None, scope="all", code=None, candidate_id=candidate_id, q="")
    return {
        "candidate": _candidate_brief(candidate),
        "submissions": [_card(row) for row in rows],
    }


@router.post("/submissions/{submission_id}/comments")
def post_submission_comment(submission_id: uuid.UUID, body: CommentIn, session: Session = Depends(require_admin)):
    return _comment_out(add_submission_comment(session, submission_id, body.body))


@router.patch("/submissions/{submission_id}/comments/{comment_id}")
def patch_submission_comment(
    submission_id: uuid.UUID,
    comment_id: uuid.UUID,
    body: CommentIn,
    session: Session = Depends(require_admin),
):
    return _comment_out(edit_submission_comment(session, submission_id, comment_id, body.body))


@router.delete("/submissions/{submission_id}/comments/{comment_id}")
def delete_submission_comment(
    submission_id: uuid.UUID,
    comment_id: uuid.UUID,
    session: Session = Depends(require_admin),
):
    remove_submission_comment(session, submission_id, comment_id)
    return {"ok": True}


@router.get("/resumes/{candidate_id}/comments")
def get_candidate_comments(candidate_id: uuid.UUID, session: Session = Depends(require_admin)):
    return {"comments": [_comment_out(row) for row in list_candidate_comments(session, candidate_id)]}


@router.post("/resumes/{candidate_id}/comments")
def post_candidate_comment(candidate_id: uuid.UUID, body: CommentIn, session: Session = Depends(require_admin)):
    return _comment_out(add_candidate_comment(session, candidate_id, body.body))


@router.patch("/resumes/{candidate_id}/comments/{comment_id}")
def patch_candidate_comment(
    candidate_id: uuid.UUID,
    comment_id: uuid.UUID,
    body: CommentIn,
    session: Session = Depends(require_admin),
):
    return _comment_out(edit_candidate_comment(session, candidate_id, comment_id, body.body))


@router.delete("/resumes/{candidate_id}/comments/{comment_id}")
def delete_candidate_comment(
    candidate_id: uuid.UUID,
    comment_id: uuid.UUID,
    session: Session = Depends(require_admin),
):
    remove_candidate_comment(session, candidate_id, comment_id)
    return {"ok": True}
