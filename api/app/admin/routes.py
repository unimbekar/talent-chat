"""Recruiter routes."""

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.sql.expression import nullslast
from sqlalchemy.orm import Session

from app.admin.auth import (
    clear_failures,
    cookie_name,
    issue_session,
    lock_status,
    read_session,
    record_failure,
    verify_password,
)
from app.admin.candidate_repository import by_hash, delete_candidate, get_candidate
from app.admin.folder_ingest import ingest_status, preferred_name, scan_resumes, start_ingest
from app.admin.rank import _posting_lines, embed_candidate, rank_jobs
from app.core.score import MANDATORY_BAR, covers_title, section_coverage
from app.config import get_settings
from app.core.client_ip import client_ip
from app.core.crawler import HttpFetcher, run_crawl
from app.core.detail_parser import DetailParse
from app.core.extract import ExtractError, extract_text
from app.core.labor import categories_for_question, labor_categories
from app.core.llm import LLMError
from app.core.files import store_original
from app.core.redact import redact_ssn
from app.core.skills import normalize_skill_list
from app.core.structure import skills_from_quotes
from app.core.structure import parse_resume_profile, structure_job
from app.core.tokens import chunk_text, job_vector_text
from app.db import get_admin_db
from app.models import AuditLog, CrawlState, Job, JobChunk, Match, SkillSynonym

router = APIRouter(prefix="/admin", tags=["admin"])


class LoginIn(BaseModel):
    password: str


class JobEdit(BaseModel):
    title: str | None = None
    location: str | None = None
    must_have_skills: list[str] | None = None
    nice_to_have_skills: list[str] | None = None
    clearance_required: str | None = None
    polygraph_required: str | None = None
    description_text: str | None = None
    needs_review: bool | None = None
    must_have_quotes: list[str] | None = None
    nice_to_have_quotes: list[str] | None = None


class AskIn(BaseModel):
    message: str


class ConfirmIn(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    skills: list[dict] = Field(default_factory=list)
    titles: list[str] = Field(default_factory=list)
    clearance: str | None = None
    polygraph: str | None = None
    citizenship: str | None = None
    summary: str | None = None
    required_skills: list[str] = Field(default_factory=list)


class SynonymIn(BaseModel):
    alias: str
    canonical: str


def _audit(session: Session, action: str, subject_id: uuid.UUID | None = None, outcome: str | None = None) -> None:
    session.add(AuditLog(actor="admin", action=action, subject_id=subject_id, outcome=outcome))


def require_admin(request: Request, session: Session = Depends(get_admin_db)) -> Session:
    token = request.cookies.get(cookie_name())
    if read_session(session, token) is None:
        raise HTTPException(status_code=401, detail="Sign in required.")
    return session


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, session: Session = Depends(get_admin_db)):
    ip = client_ip(request, get_settings())
    if lock_status(session, ip):
        raise HTTPException(status_code=429, detail="Too many sign-in attempts. Try again in 15 minutes.")
    if not verify_password(body.password):
        record_failure(session, ip)
        _audit(session, "login", outcome="denied")
        session.commit()
        raise HTTPException(status_code=401, detail="Incorrect password.")
    clear_failures(session, ip)
    token = issue_session(session)
    _audit(session, "login", outcome="ok")
    session.commit()
    settings = get_settings()
    response.set_cookie(
        cookie_name(),
        token,
        httponly=True,
        samesite="lax",
        max_age=12 * 3600,
        secure=settings.session_secure,
        path="/",
    )
    return {"ok": True}


@router.post("/logout")
def logout(response: Response, session: Session = Depends(require_admin)):
    _audit(session, "logout", outcome="ok")
    session.commit()
    response.delete_cookie(cookie_name(), path="/")
    return {"ok": True}


@router.get("/jobs")
def list_jobs(session: Session = Depends(require_admin)):
    jobs = session.scalars(select(Job).order_by(Job.requisition_code)).all()
    state = session.get(CrawlState, 1)
    return {
        "crawl": {
            "last_ok": None if state is None else state.last_ok,
            "last_error": None if state is None else state.last_error,
            "last_finished_at": None if state is None or state.last_finished_at is None else state.last_finished_at.isoformat(),
            "last_rows": None if state is None else state.last_rows,
        },
        "jobs": [_job_out(job) for job in jobs],
    }


@router.get("/jobs/{code}")
def get_job(code: str, session: Session = Depends(require_admin)):
    job = session.scalar(select(Job).where(Job.requisition_code == code))
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return _job_out(job)


@router.get("/jobs/{code}/candidates")
def job_candidates(code: str, session: Session = Depends(require_admin)):
    from app.core.structure import resume_facts
    from app.models import Candidate

    job = session.scalar(select(Job).where(Job.requisition_code == code))
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    must_lines = _posting_lines(job, "must", list(job.must_have_skills or []))
    nice_lines = _posting_lines(job, "nice", list(job.nice_to_have_skills or []))
    ranked: list[dict] = []
    for candidate in session.scalars(select(Candidate).order_by(Candidate.created_at.desc())).all():
        facts = resume_facts(candidate.redacted_text or "")
        names = {item["name"] for item in facts["skills"]}
        if not names:
            names = {skill["name"] if isinstance(skill, dict) else str(skill) for skill in (candidate.skills or [])}
        display_name = _person_name(candidate, facts)
        text = candidate.redacted_text or ""
        mandatory = section_coverage(names, must_lines, text)
        desired = section_coverage(names, nice_lines, text)
        if not covers_title(names, job.title):
            mandatory = {**mandatory, "pct": 0.0, "hit": 0, "matched": []}
        mandatory_pct = mandatory["pct"]
        ranked.append(
            {
                "id": str(candidate.id),
                "full_name": display_name or candidate.full_name,
                "original_filename": candidate.original_filename,
                "mandatory_pct": mandatory_pct,
                "mandatory_hit": mandatory["hit"],
                "mandatory_total": mandatory["total"],
                "desired_pct": desired["pct"],
                "desired_hit": desired["hit"],
                "desired_total": desired["total"],
                "desired_any": desired["hit"] > 0,
                "meets_bar": mandatory_pct is not None and mandatory_pct >= MANDATORY_BAR,
            }
        )
    ranked.sort(
        key=lambda item: (
            1 if item["meets_bar"] else 0,
            item["mandatory_pct"] if item["mandatory_pct"] is not None else -1,
            1 if item["desired_any"] else 0,
            item["desired_pct"] if item["desired_pct"] is not None else -1,
        ),
        reverse=True,
    )
    ranked = [item for item in ranked if item["mandatory_pct"] is not None and item["mandatory_pct"] >= 0.5]
    return {"candidates": ranked}


@router.get("/review")
def review_pair(code: str, candidate_id: uuid.UUID, session: Session = Depends(require_admin)):
    from app.core.skills import tools_and_languages
    from app.core.structure import resume_facts
    from app.models import Candidate

    job = session.scalar(select(Job).where(Job.requisition_code == code))
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    candidate = session.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    facts = resume_facts(candidate.redacted_text or "")
    names = {item["name"] for item in facts["skills"]}
    if not names:
        names = {skill["name"] if isinstance(skill, dict) else str(skill) for skill in (candidate.skills or [])}
    text = candidate.redacted_text or ""
    must_lines = _posting_lines(job, "must", list(job.must_have_skills or []))
    nice_lines = _posting_lines(job, "nice", list(job.nice_to_have_skills or []))
    mandatory = section_coverage(names, must_lines, text)
    desired = section_coverage(names, nice_lines, text)
    have = {name.lower() for name in names}
    title_missing = [tool for tool in tools_and_languages(job.title or "") if tool.lower() not in have]
    mandatory_pct = mandatory["pct"]
    return {
        "job": {"requisition_code": job.requisition_code, "title": job.title, "location": job.location},
        "candidate": {
            "id": str(candidate.id),
            "full_name": _person_name(candidate, facts),
            "original_filename": candidate.original_filename,
        },
        "mandatory_pct": mandatory_pct,
        "mandatory_hit": mandatory["hit"],
        "mandatory_total": mandatory["total"],
        "desired_pct": desired["pct"],
        "desired_hit": desired["hit"],
        "desired_total": desired["total"],
        "meets_bar": mandatory_pct is not None and mandatory_pct >= MANDATORY_BAR and not title_missing,
        "title_missing": title_missing,
        "mandatory_matched": mandatory["matched"],
        "mandatory_missing": mandatory["missing"],
        "desired_matched": desired["matched"],
        "desired_missing": desired["missing"],
    }


@router.post("/jobs/recrawl")
def recrawl(request: Request, session: Session = Depends(require_admin)):
    settings = get_settings()
    open_before = set(session.scalars(select(Job.requisition_code).where(Job.status != "closed")).all())
    fetcher = HttpFetcher(timeout=20, delay_seconds=settings.crawl_request_delay_seconds)
    state = run_crawl(session, fetcher, settings.careers_url, request.app.state.llm, request.app.state.embedder)
    session.expire_all()
    open_after = set(session.scalars(select(Job.requisition_code).where(Job.status != "closed")).all())
    closed_codes = sorted(open_before - open_after)
    _audit(session, "recrawl", outcome="ok" if state.last_ok else "error")
    session.commit()
    return {
        "last_ok": state.last_ok,
        "last_error": state.last_error,
        "last_rows": state.last_rows,
        "closed_codes": closed_codes,
    }


@router.put("/jobs/{code}")
def edit_job(code: str, body: JobEdit, request: Request, session: Session = Depends(require_admin)):
    job = session.scalar(select(Job).where(Job.requisition_code == code))
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if body.title is not None:
        job.title = body.title
    if body.location is not None:
        job.location = body.location
    if body.must_have_skills is not None:
        job.must_have_skills = normalize_skill_list(body.must_have_skills)
    if body.nice_to_have_skills is not None:
        job.nice_to_have_skills = normalize_skill_list(body.nice_to_have_skills)
    if body.clearance_required is not None:
        job.clearance_required = body.clearance_required or None
    if body.polygraph_required is not None:
        job.polygraph_required = body.polygraph_required or None
    if body.needs_review is not None:
        job.needs_review = body.needs_review
    if body.description_text is not None:
        _apply_admin_description(session, job, redact_ssn(body.description_text), request)
    if body.must_have_quotes is not None or body.nice_to_have_quotes is not None:
        quotes = dict(job.skill_quotes or {})
        if body.must_have_quotes is not None:
            quotes["must"] = [line.strip() for line in body.must_have_quotes if line.strip()]
            job.must_have_skills = skills_from_quotes(quotes["must"])
        if body.nice_to_have_quotes is not None:
            quotes["nice"] = [line.strip() for line in body.nice_to_have_quotes if line.strip()]
            job.nice_to_have_skills = skills_from_quotes(quotes["nice"])
        job.skill_quotes = quotes
    _audit(session, "job_edit", job.id, "ok")
    session.commit()
    return _job_out(job)


@router.post("/jobs/{code}/description")
async def upload_description(
    code: str,
    request: Request,
    session: Session = Depends(require_admin),
    file: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
):
    job = session.scalar(select(Job).where(Job.requisition_code == code))
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if file is not None and file.filename:
        data = await file.read()
        try:
            extracted = extract_text(file.filename, data)
        except ExtractError as exc:
            raise HTTPException(status_code=400, detail=exc.message) from exc
        body = extracted
    elif text is not None:
        body = text
    else:
        raise HTTPException(status_code=400, detail="Paste a description or upload a file.")
    _apply_admin_description(session, job, redact_ssn(body), request)
    _audit(session, "job_description", job.id, "admin")
    session.commit()
    return _job_out(job)


@router.post("/synonyms")
def add_synonym(body: SynonymIn, session: Session = Depends(require_admin)):
    alias = body.alias.strip()
    canonical = body.canonical.strip()
    if not alias or not canonical:
        raise HTTPException(status_code=400, detail="Alias and canonical name are required.")
    existing = session.get(SkillSynonym, {"alias": alias, "canonical": canonical})
    if existing is None:
        session.add(SkillSynonym(alias=alias, canonical=canonical))
    _audit(session, "synonym_add", outcome=canonical)
    session.commit()
    return {"alias": alias, "canonical": canonical}


class _TextOnlyLLM:
    """Folder import fills the profile from the file text and does not call the model."""

    def complete(self, *, system: str, user: str, temperature: float, json_mode: bool) -> str:
        raise LLMError("folder import reads the résumé text")


def _store_resume(
    session: Session,
    filename: str,
    data: bytes,
    llm,
    *,
    refresh: bool = False,
    extra_categories: list[str] | None = None,
    email_hint: str | None = None,
) -> dict:
    digest = hashlib.sha256(data).hexdigest()
    existing = by_hash(session, digest)
    if existing is not None and not refresh:
        _audit(session, "resume_upload", existing.id, "already_ingested")
        session.commit()
        return {"already_ingested": True, "candidate_id": str(existing.id), "message": "already ingested"}
    try:
        text = extract_text(filename or "resume.txt", data)
    except ExtractError as exc:
        _audit(session, "resume_upload", outcome="rejected")
        session.commit()
        raise HTTPException(status_code=400, detail=exc.message) from exc
    redacted = redact_ssn(text)
    path = store_original(data, digest)
    profile = parse_resume_profile(redacted, llm)
    if email_hint and _company_email(profile.get("email")):
        profile["email"] = email_hint
    categories = labor_categories(filename or "", redacted)
    for label in extra_categories or []:
        if label not in categories:
            categories.append(label)
    if categories:
        profile["titles"] = categories[:4]
    if existing is not None:
        _fill_candidate(existing, digest, filename or "resume", str(path), redacted, profile, keep_status=True)
        _audit(session, "resume_upload", existing.id, "refreshed")
        session.commit()
        return {"already_ingested": True, "refreshed": True, "candidate_id": str(existing.id)}
    name = preferred_name(profile.get("full_name"), filename)
    twin = _by_name(session, name) if refresh and name else None
    if twin is not None:
        _fill_candidate(twin, digest, filename or "resume", str(path), redacted, profile, keep_status=True)
        _audit(session, "resume_upload", twin.id, "refreshed")
        session.commit()
        return {"already_ingested": True, "refreshed": True, "candidate_id": str(twin.id)}
    candidate = _new_candidate(digest, filename or "resume", str(path), redacted, profile)
    session.add(candidate)
    session.flush()
    _audit(session, "resume_upload", candidate.id, "accepted")
    session.commit()
    return {"already_ingested": False, "candidate": _candidate_out(candidate)}


@router.post("/resumes")
async def upload_resume(
    request: Request,
    session: Session = Depends(require_admin),
    file: UploadFile = File(...),
):
    data = await file.read()
    return _store_resume(session, file.filename or "resume.txt", data, request.app.state.llm)


def _resume_root() -> Path:
    folder = get_settings().resume_folder.strip()
    if not folder:
        raise HTTPException(status_code=400, detail="No résumé folder is configured.")
    root = Path(folder)
    if not root.is_dir():
        raise HTTPException(status_code=400, detail="The résumé folder is not available.")
    return root


@router.get("/ingest/scan")
def ingest_scan(session: Session = Depends(require_admin)):
    del session
    scan = scan_resumes(_resume_root())
    preview = [
        {"label": item.label, "file": item.path.name, "older": len(item.older)}
        for item in scan.chosen[:12]
    ]
    return {
        "people": len(scan.chosen),
        "older": scan.older,
        "ignored": scan.ignored,
        "preview": preview,
    }


@router.post("/ingest/start")
def ingest_start(session: Session = Depends(require_admin)):
    del session
    root = _resume_root()

    def save(path):
        from app.db import admin_session

        db = admin_session()
        try:
            try:
                result = _store_resume(db, path.name, path.read_bytes(), _TextOnlyLLM(), refresh=True)
            except HTTPException as exc:
                raise RuntimeError(str(exc.detail)) from exc
        finally:
            db.close()
        return "already" if result["already_ingested"] and not result.get("refreshed") else "imported"

    if not start_ingest(root, save):
        raise HTTPException(status_code=409, detail="An import is already running.")
    return {"ok": True}


@router.get("/ingest/status")
def ingest_progress(session: Session = Depends(require_admin)):
    del session
    return ingest_status()


@router.post("/resumes/{candidate_id}/confirm")
def confirm_resume(
    candidate_id: uuid.UUID,
    body: ConfirmIn,
    request: Request,
    session: Session = Depends(require_admin),
):
    candidate = get_candidate(session, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    candidate.full_name = body.full_name
    candidate.email = body.email
    candidate.phone = body.phone
    candidate.location = body.location
    from app.core.skills import tools_and_languages

    phrases = [item.get("name", "") if isinstance(item, dict) else str(item) for item in body.skills]
    names = tools_and_languages("\n".join(phrases), allow_unknown=True)
    years = {}
    for item in body.skills:
        if isinstance(item, dict) and item.get("name"):
            years[str(item["name"]).lower()] = item.get("years")
    candidate.skills = [{"name": name, "years": years.get(name.lower())} for name in names]
    submitted_titles = [title for title in body.titles if title and title.strip()]
    if submitted_titles:
        candidate.titles = submitted_titles
    elif not candidate.titles:
        candidate.titles = labor_categories(candidate.original_filename or "", candidate.redacted_text or "")
    candidate.clearance = body.clearance or None
    candidate.polygraph = body.polygraph or None
    candidate.citizenship = body.citizenship
    candidate.summary = body.summary
    candidate.status = "confirmed"
    embed_candidate(session, candidate, request.app.state.embedder)
    session.flush()
    matches = rank_jobs(
        session,
        candidate,
        request.app.state.embedder,
        request.app.state.llm,
        required_skills=body.required_skills,
    )
    _audit(session, "resume_confirm", candidate.id, "ok")
    session.commit()
    return {
        "candidate": _candidate_out(candidate),
        "matches": [_match_out(session, row, body.required_skills) for row in matches],
    }


@router.delete("/resumes/{candidate_id}")
def remove_resume(candidate_id: uuid.UUID, session: Session = Depends(require_admin)):
    candidate = get_candidate(session, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    _audit(session, "resume_delete", candidate.id, "ok")
    delete_candidate(session, candidate)
    session.commit()
    return {"ok": True}


@router.get("/resumes")
def list_resumes(
    session: Session = Depends(require_admin),
    q: str = "",
    category: str = "",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
):
    from app.models import Candidate

    stmt = select(Candidate)
    term = q.strip()
    if term:
        pattern = f"%{term.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')}%"
        stmt = stmt.where(
            or_(
                Candidate.full_name.ilike(pattern, escape="\\"),
                Candidate.email.ilike(pattern, escape="\\"),
                Candidate.original_filename.ilike(pattern, escape="\\"),
                Candidate.location.ilike(pattern, escape="\\"),
                cast(Candidate.skills, String).ilike(pattern, escape="\\"),
                cast(Candidate.titles, String).ilike(pattern, escape="\\"),
                Candidate.redacted_text.ilike(pattern, escape="\\"),
            )
        )
    labels = categories_for_question(category) if category.strip() else []
    if labels:
        stmt = stmt.where(or_(*(cast(Candidate.titles, String).ilike(f"%{label}%") for label in labels)))
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = session.scalars(
        stmt.order_by(nullslast(func.lower(Candidate.full_name)), Candidate.original_filename)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "candidates": [
            {
                "id": str(row.id),
                "full_name": _person_name(row),
                "email": row.email,
                "location": row.location,
                "original_filename": row.original_filename,
                "status": row.status,
                "titles": list(row.titles or []),
                "skills": [
                    item.get("name")
                    for item in (row.skills or [])
                    if isinstance(item, dict) and item.get("name")
                ][:6],
            }
            for row in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/candidates/ask")
def ask_candidates(body: AskIn, session: Session = Depends(require_admin)):
    """Answer a recruiter question such as 'Show me all Software Testers.'"""
    from app.models import Candidate

    message = body.message.strip()
    labels = categories_for_question(message)
    stmt = select(Candidate)
    if labels:
        stmt = stmt.where(or_(*(cast(Candidate.titles, String).ilike(f"%{label}%") for label in labels)))
    elif message:
        pattern = f"%{message.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')}%"
        stmt = stmt.where(
            or_(
                Candidate.full_name.ilike(pattern, escape="\\"),
                cast(Candidate.skills, String).ilike(pattern, escape="\\"),
                Candidate.redacted_text.ilike(pattern, escape="\\"),
            )
        )
    rows = session.scalars(stmt.order_by(nullslast(func.lower(Candidate.full_name))).limit(200)).all()
    if labels:
        answer = f"{len(rows)} {'person' if len(rows) == 1 else 'people'} in {', '.join(labels)}."
    elif message:
        answer = f"{len(rows)} {'person' if len(rows) == 1 else 'people'} matched that search."
    else:
        answer = "Ask for a category, such as Software Testers or Cybersecurity Engineers."
    return {
        "answer": answer,
        "categories": labels,
        "candidates": [
            {
                "id": str(row.id),
                "full_name": _person_name(row),
                "email": row.email,
                "location": row.location,
                "titles": list(row.titles or []),
                "skills": [
                    item.get("name")
                    for item in (row.skills or [])
                    if isinstance(item, dict) and item.get("name")
                ][:6],
            }
            for row in rows
        ],
    }


@router.get("/resumes/{candidate_id}")
def get_resume(candidate_id: uuid.UUID, session: Session = Depends(require_admin)):
    candidate = get_candidate(session, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    matches = session.scalars(select(Match).where(Match.candidate_id == candidate.id)).all()
    payload = [_match_out(session, row) for row in matches]
    payload.sort(key=_coverage_sort, reverse=True)
    return {"candidate": _candidate_out(candidate), "matches": payload}


def _company_email(email: str | None) -> bool:
    text = (email or "").strip().lower()
    return not text or text.endswith("@janus-soft.com")


def _by_name(session: Session, name: str):
    from app.models import Candidate

    return session.scalar(select(Candidate).where(func.lower(Candidate.full_name) == name.lower()))


def _fill_candidate(candidate, digest: str, filename: str, path: str, redacted: str, profile: dict, *, keep_status: bool) -> None:
    candidate.file_sha256 = digest
    candidate.original_filename = filename
    candidate.original_path = path
    candidate.full_name = preferred_name(profile.get("full_name"), filename)
    candidate.email = profile.get("email") or candidate.email
    candidate.phone = profile.get("phone") or candidate.phone
    candidate.location = profile.get("location") or candidate.location
    candidate.skills = profile.get("skills") or candidate.skills or []
    candidate.titles = profile.get("titles") or []
    candidate.clearance = profile.get("clearance") or candidate.clearance
    candidate.polygraph = profile.get("polygraph") or candidate.polygraph
    candidate.citizenship = profile.get("citizenship") or candidate.citizenship
    candidate.summary = profile.get("summary") or candidate.summary
    candidate.redacted_text = redacted
    if not keep_status:
        candidate.status = "pending_review"


def _new_candidate(digest: str, filename: str, path: str, redacted: str, profile: dict):
    from app.models import Candidate

    return Candidate(
        file_sha256=digest,
        original_filename=filename,
        original_path=path,
        status="pending_review",
        full_name=preferred_name(profile.get("full_name"), filename),
        email=profile.get("email"),
        phone=profile.get("phone"),
        location=profile.get("location"),
        skills=profile.get("skills") or [],
        titles=profile.get("titles") or [],
        clearance=profile.get("clearance"),
        polygraph=profile.get("polygraph"),
        citizenship=profile.get("citizenship"),
        summary=profile.get("summary"),
        redacted_text=redacted,
        outreach_opt_in=False,
    )


def _apply_admin_description(session: Session, job: Job, text: str, request: Request) -> None:
    parsed = DetailParse(
        description_text=text,
        must_have_quotes=[],
        nice_to_have_quotes=[],
        needs_review=False,
    )
    structured = structure_job(parsed, request.app.state.llm)
    job.description_text = structured["description_text"]
    job.description_source = "admin"
    job.description_hash = hashlib.sha256(job.description_text.encode("utf-8")).hexdigest()
    job.must_have_skills = structured["must_have_skills"] or job.must_have_skills
    job.nice_to_have_skills = structured["nice_to_have_skills"] or job.nice_to_have_skills
    if structured["clearance_required"]:
        job.clearance_required = structured["clearance_required"]
    if structured["polygraph_required"]:
        job.polygraph_required = structured["polygraph_required"]
    if structured["summary"]:
        job.summary = structured["summary"]
    job.skill_quotes = structured["skill_quotes"]
    try:
        session.query(JobChunk).filter(JobChunk.job_id == job.id).delete()
        chunks = chunk_text(job.description_text or "")
        vectors = request.app.state.embedder.embed_documents(chunks) if chunks else []
        for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
            session.add(JobChunk(job_id=job.id, ord=index, text=chunk, embedding=vector))
        whole = job_vector_text(job.title or "", job.location or "", job.summary or "", job.description_text or "")
        embedded = request.app.state.embedder.embed_documents([whole])
        job.embedding = embedded[0] if embedded else None
    except Exception:
        job.embedding = job.embedding


def _job_out(job: Job) -> dict:
    return {
        "requisition_code": job.requisition_code,
        "site_job_id": job.site_job_id,
        "title": job.title,
        "location": job.location,
        "status": job.status,
        "program_tag": job.program_tag,
        "external_req": job.external_req,
        "needs_review": job.needs_review,
        "description_source": job.description_source,
        "description_text": job.description_text,
        "description_note": None if (job.description_text or "").strip() else "Full description not on file.",
        "must_have_skills": job.must_have_skills or [],
        "nice_to_have_skills": job.nice_to_have_skills or [],
        "must_have_quotes": list((job.skill_quotes or {}).get("must") or []),
        "nice_to_have_quotes": list((job.skill_quotes or {}).get("nice") or []),
        "clearance_required": job.clearance_required,
        "polygraph_required": job.polygraph_required,
        "summary": job.summary,
        "source_line": job.source_line,
        "source_url": job.source_url,
        "detail_error": job.detail_error,
        "last_seen_at": job.last_seen_at.isoformat() if job.last_seen_at else None,
        "confidence": "low" if not (job.description_text or "").strip() else "standard",
    }


def _tool_skills(candidate) -> list[dict]:
    from app.core.structure import resume_facts

    stored = candidate.skills or []
    years = {}
    for item in stored:
        if isinstance(item, dict) and item.get("name"):
            years[str(item["name"]).lower()] = item.get("years")
    names = [item["name"] for item in resume_facts(candidate.redacted_text or "")["skills"]]
    return [{"name": name, "years": years.get(name.lower())} for name in names]


def _person_name(candidate, facts: dict | None = None) -> str | None:
    stored = (candidate.full_name or "").strip()
    if (not stored or "clearance" in stored.lower()) and facts is None:
        from app.core.structure import resume_facts

        facts = resume_facts(candidate.redacted_text or "")
    if facts is not None:
        parsed = (facts.get("full_name") or "").strip()
        if parsed and "clearance" not in parsed.lower():
            stored = parsed
    return preferred_name(stored, candidate.original_filename)


def _candidate_out(candidate) -> dict:
    return {
        "id": str(candidate.id),
        "status": candidate.status,
        "full_name": _person_name(candidate),
        "email": candidate.email,
        "phone": candidate.phone,
        "location": candidate.location,
        "skills": _tool_skills(candidate),
        "titles": candidate.titles or [],
        "clearance": candidate.clearance,
        "polygraph": candidate.polygraph,
        "citizenship": candidate.citizenship,
        "summary": candidate.summary,
    }


def _coverage_sort(item: dict) -> tuple:
    return (
        1 if item["meets_bar"] else 0,
        item["mandatory_pct"] if item["mandatory_pct"] is not None else -1,
        1 if item["desired_any"] else 0,
        item["desired_pct"] if item["desired_pct"] is not None else -1,
        item["final"] or 0,
    )


def _stored_coverage(session: Session, row: Match, job: Job | None, required_skills: list[str]) -> dict:
    from app.core.score import required_coverage
    from app.models import Candidate

    from app.core.structure import resume_facts

    names: set[str] = set()
    text = ""
    candidate = session.get(Candidate, row.candidate_id)
    if candidate is not None:
        text = candidate.redacted_text or ""
        names = {item["name"] for item in resume_facts(text)["skills"]}
        if not names:
            names = {skill["name"] if isinstance(skill, dict) else str(skill) for skill in (candidate.skills or [])}
    must_lines = [] if job is None else _posting_lines(job, "must", list(job.must_have_skills or []))
    nice_lines = [] if job is None else _posting_lines(job, "nice", list(job.nice_to_have_skills or []))
    mandatory = section_coverage(names, must_lines, text)
    desired = section_coverage(names, nice_lines, text)
    if job is not None and not covers_title(names, job.title):
        mandatory = {**mandatory, "pct": 0.0, "hit": 0, "matched": []}
    required = required_coverage(names, must_lines, required_skills)
    mandatory_pct = mandatory["pct"]
    return {
        "mandatory_pct": mandatory_pct,
        "mandatory_hit": mandatory["hit"],
        "mandatory_total": mandatory["total"],
        "desired_pct": desired["pct"],
        "desired_hit": desired["hit"],
        "desired_total": desired["total"],
        "desired_any": desired["hit"] > 0,
        "required_pct": required["pct"],
        "required_matched": required["matched"],
        "required_missing": required["missing"],
        "meets_bar": mandatory_pct is not None and mandatory_pct >= MANDATORY_BAR and not required["missing"],
    }


def _match_out(session: Session, row: Match, required_skills: list[str] | None = None) -> dict:
    job = session.get(Job, row.job_id)
    coverage = _stored_coverage(session, row, job, required_skills or [])
    return {
        "requisition_code": None if job is None else job.requisition_code,
        "title": None if job is None else job.title,
        "location": None if job is None else job.location,
        "final": row.final,
        "skill_score": row.skill_score,
        "semantic": row.semantic,
        "overlap_skills": row.overlap_skills or [],
        "clearance_flag": row.clearance_flag,
        "confidence": row.confidence,
        "job_quotes": row.job_quotes or [],
        "resume_quotes": row.resume_quotes or [],
        "explanation": row.explanation,
        **coverage,
        "description_note": None
        if job is not None and (job.description_text or "").strip()
        else "Full description not on file.",
    }
