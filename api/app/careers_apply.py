"""A visitor applies for one open job. The résumé is stored and the pipeline shows Submitted.

The public database role cannot write candidates or submissions. This module uses the
recruiter role on the server. The visitor never receives a recruiter session.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import re
import threading
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin.pipeline import SALARY_MAX
from app.admin.routes import _store_resume
from app.models import AuditLog, Job, JobApplication, Submission, SubmissionComment, SubmissionEvent

_LOCK = threading.Lock()
_HITS: dict[str, list[datetime]] = defaultdict(list)
_LIMIT = 8
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def reset_apply_limit() -> None:
    with _LOCK:
        _HITS.clear()


def limited(ip: str) -> bool:
    now = datetime.now(timezone.utc)
    window = now - timedelta(hours=1)
    with _LOCK:
        recent = [stamp for stamp in _HITS[ip] if stamp > window]
        if len(recent) >= _LIMIT:
            _HITS[ip] = recent
            return True
        recent.append(now)
        _HITS[ip] = recent
        return False


def _fail(status: int, message: str) -> None:
    raise HTTPException(status_code=status, detail={"message": message})


def _day(value: str, *, required: bool, label: str) -> date | None:
    text = (value or "").strip()
    if not text:
        if required:
            _fail(400, f"{label} is required.")
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        _fail(400, f"{label} must be a calendar date.")
        return None


def submit_application(
    session: Session,
    *,
    llm,
    requisition_code: str,
    full_name: str,
    email: str,
    phone: str,
    location: str,
    salary_usd: int,
    start_on: str,
    years_experience: int,
    fsp: str,
    last_fsp_on: str,
    last_tssci_on: str,
    note: str,
    filename: str,
    data: bytes,
) -> dict:
    code = requisition_code.strip()
    name = " ".join(full_name.split())
    mail = email.strip().lower()
    phone_text = " ".join(phone.split())
    place = " ".join(location.split())
    remark = " ".join(note.split())
    if not code:
        _fail(400, "Choose a job.")
    if len(name) < 2 or len(name) > 120:
        _fail(400, "Enter your name.")
    if not _EMAIL.match(mail) or len(mail) > 200:
        _fail(400, "Enter an email address.")
    if len(phone_text) < 7 or len(phone_text) > 40:
        _fail(400, "Enter a phone number.")
    if len(place) < 2 or len(place) > 120:
        _fail(400, "Enter the city where you live.")
    if salary_usd < 1 or salary_usd > SALARY_MAX:
        _fail(400, "Desired salary must be between 1 and 5,000,000 dollars a year.")
    if years_experience < 0 or years_experience > 60:
        _fail(400, "Years of experience must be between 0 and 60.")
    if len(remark) > 1000:
        _fail(400, "Keep the note under 1,000 characters.")
    holds_fsp = fsp.strip().lower() in {"yes", "y", "true"}
    if not holds_fsp:
        _fail(
            400,
            "This firm can submit only candidates who currently hold TS/SCI with a Full Scope Polygraph (FSP).",
        )
    start = _day(start_on, required=True, label="The date you can start")
    assert start is not None
    today = datetime.now(timezone.utc).date()
    if start < today - timedelta(days=7) or start > today + timedelta(days=540):
        _fail(400, "Choose a start date from this week through the next 18 months.")
    fsp_on = _day(last_fsp_on, required=False, label="Last FSP date")
    ts_on = _day(last_tssci_on, required=False, label="Last TS/SCI date")
    for label, found in (("Last FSP date", fsp_on), ("Last TS/SCI date", ts_on)):
        if found is not None and (found > today or found.year < 1980):
            _fail(400, f"{label} has to be a past date.")
    if not data:
        _fail(400, "Upload a PDF, DOC, DOCX, or TXT résumé.")

    job = session.scalar(select(Job).where(Job.requisition_code == code))
    if job is None:
        _fail(404, "That job is not on file.")
    if job.status != "open":
        _fail(400, "That job is no longer open.")

    try:
        stored = _store_resume(session, filename or "resume.txt", data, llm, email_hint=mail)
    except HTTPException as exc:
        detail = exc.detail
        message = detail.get("message") if isinstance(detail, dict) else str(detail)
        _fail(exc.status_code, message or "The résumé could not be read.")
    raw_id = stored.get("candidate_id") or (stored.get("candidate") or {}).get("id")
    from app.models import Candidate

    try:
        candidate_id = uuid.UUID(str(raw_id))
    except (TypeError, ValueError):
        candidate_id = None
    candidate = None if candidate_id is None else session.get(Candidate, candidate_id)
    if candidate is None:
        _fail(500, "The résumé was not saved.")
    candidate.full_name = name
    candidate.email = mail
    candidate.phone = phone_text
    candidate.location = place
    candidate.clearance = "ts_sci"
    candidate.polygraph = "full_scope"

    salary_note = f"Careers site. Can start {start.isoformat()}. {years_experience} years."
    now = datetime.now(timezone.utc)
    row = session.scalar(select(Submission).where(Submission.candidate_id == candidate.id, Submission.job_id == job.id))
    created = row is None
    if row is None:
        row = Submission(
            candidate_id=candidate.id,
            job_id=job.id,
            stage="submitted",
            salary_usd=salary_usd,
            salary_note=salary_note,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.flush()
        session.add(
            SubmissionEvent(
                submission_id=row.id,
                kind="created",
                to_stage="submitted",
                body="Applied on the careers site.",
                salary_usd=salary_usd,
                at=now,
            )
        )
    else:
        previous = row.stage
        row.salary_usd = salary_usd
        row.salary_note = salary_note
        row.updated_at = now
        if previous in {"rejected", "withdrawn"}:
            row.stage = "submitted"
            session.add(
                SubmissionEvent(
                    submission_id=row.id,
                    kind="stage",
                    from_stage=previous,
                    to_stage="submitted",
                    body="Reapplied on the careers site.",
                    salary_usd=salary_usd,
                    at=now,
                )
            )
        else:
            session.add(
                SubmissionEvent(
                    submission_id=row.id,
                    kind="salary",
                    from_stage=previous,
                    to_stage=previous,
                    body="Updated from a careers-site application.",
                    salary_usd=salary_usd,
                    at=now,
                )
            )

    application = session.scalar(select(JobApplication).where(JobApplication.submission_id == row.id))
    if application is None:
        application = JobApplication(submission_id=row.id, candidate_id=candidate.id, job_id=job.id, fsp=True)
        session.add(application)
    application.full_name = name
    application.email = mail
    application.phone = phone_text
    application.location = place
    application.salary_usd = salary_usd
    application.start_on = start
    application.years_experience = years_experience
    application.fsp = True
    application.last_fsp_on = fsp_on
    application.last_tssci_on = ts_on
    application.note = remark or None
    dates = []
    if ts_on:
        dates.append(f"Last TS/SCI {ts_on.isoformat()}")
    if fsp_on:
        dates.append(f"Last FSP {fsp_on.isoformat()}")
    comment = (
        f"Applied on the careers site. {name}, {mail}, {phone_text}, {place}. "
        f"Desired salary ${salary_usd:,}. Can start {start.isoformat()}. {years_experience} years. "
        f"Attested TS/SCI with Full Scope Polygraph."
        + (f" {' · '.join(dates)}." if dates else "")
        + (f" Note: {remark}" if remark else "")
    )
    session.add(SubmissionComment(submission_id=row.id, body=comment[:4000], created_at=now, updated_at=now))
    session.add(AuditLog(actor="careers", action="job_application", subject_id=row.id, outcome="submitted"))
    session.commit()
    return {
        "ok": True,
        "created": created,
        "requisition_code": job.requisition_code,
        "title": job.title,
        "message": (
            f"You are submitted for {job.requisition_code}. A recruiter can see this in the pipeline."
            if created
            else f"Your application for {job.requisition_code} is updated. It stays in the pipeline."
        ),
    }
