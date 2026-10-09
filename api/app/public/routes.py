"""Public HTTP routes. No candidate reads."""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import logging
import re
import threading

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.core.llm import LLMError, parse_json_content
from app.db import admin_session, public_session
from app.models import Job
from app.careers_apply import limited as apply_limited
from app.careers_apply import submit_application
from app.public.refusal import REFUSAL_TEXT, is_refusal
from app.public.search import drop_unknown_codes, search_jobs

router = APIRouter(prefix="/public", tags=["public"])
logger = logging.getLogger("talent")

_LOCK = threading.Lock()
_HITS: dict[str, list[datetime]] = defaultdict(list)
_LIMIT = 30


class HistoryTurn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=800)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    prior_codes: list[str] = Field(default_factory=list)
    history: list[HistoryTurn] = Field(default_factory=list, max_length=8)
    # False returns the job cards at once and leaves the paragraph to POST /public/explain.
    explain: bool = True


class ExplainIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    prior_codes: list[str] = Field(default_factory=list, max_length=48)
    codes: list[str] = Field(min_length=1, max_length=24)
    history: list[HistoryTurn] = Field(default_factory=list, max_length=8)


def _client_ip(request: Request) -> str:
    from app.core.client_ip import client_ip

    return client_ip(request, get_settings())


def _limited(ip: str) -> bool:
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


def reset_rate_limit() -> None:
    with _LOCK:
        _HITS.clear()


def _public_blurb(text: str | None) -> str:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    kept = [
        part.strip()
        for part in parts
        if part.strip() and not re.search(r"(?i)clearance|polygraph|top secret|ts/sci", part)
    ]
    return " ".join(kept)[:240]


@router.get("/jobs")
def list_jobs():
    """Open postings a visitor can read and apply for. No candidate data."""
    db = public_session()
    try:
        rows = db.scalars(select(Job).where(Job.status == "open").order_by(Job.title, Job.requisition_code)).all()
        return {
            "jobs": [
                {
                    "requisition_code": job.requisition_code,
                    "title": job.title,
                    "location": job.location,
                    "blurb": _public_blurb(
                        "\n".join(part for part in _posting_paragraphs(job) if len(part) > 60) or job.description_text
                    ),
                }
                for job in rows
            ]
        }
    except SQLAlchemyError:
        return JSONResponse({"message": "The job list is unavailable right now.", "jobs": []}, status_code=503)
    finally:
        db.close()


def _posting_paragraphs(job: Job) -> list[str]:
    """The careers-page posting split into paragraphs, without the page chrome the crawl picked up."""
    paragraphs: list[str] = []
    seen: set[str] = set()
    title = (job.title or "").strip().lower()
    for raw in re.split(r"\n\s*\n|\n", job.careers_description_text or ""):
        text = re.sub(r"[ \t]+", " ", raw).strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        if not paragraphs and (key in {"career", "careers"} or (title and key.startswith(title) and len(text) < 120)):
            continue
        paragraphs.append(text)
    return paragraphs


@router.get("/jobs/{requisition_code}")
def job_detail(requisition_code: str):
    """One open posting as published on the careers page. The recruiter's internal description is never sent."""
    db = public_session()
    try:
        job = db.scalars(
            select(Job).where(Job.requisition_code == requisition_code.strip(), Job.status == "open")
        ).first()
        if job is None:
            return JSONResponse({"message": "That role is not open."}, status_code=404)
        paragraphs = _posting_paragraphs(job)
        return {
            "requisition_code": job.requisition_code,
            "title": job.title,
            "location": job.location,
            "paragraphs": paragraphs,
            "description_note": None if paragraphs else "Full description not on file.",
            "source_url": job.source_url,
        }
    except SQLAlchemyError:
        return JSONResponse({"message": "The job list is unavailable right now."}, status_code=503)
    finally:
        db.close()


@router.post("/apply")
async def apply(
    request: Request,
    requisition_code: str = Form(""),
    full_name: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    location: str = Form(""),
    salary_usd: int = Form(0),
    start_on: str = Form(""),
    years_experience: int = Form(-1),
    fsp: str = Form(""),
    last_fsp_on: str = Form(""),
    last_tssci_on: str = Form(""),
    note: str = Form(""),
    file: UploadFile | None = File(default=None),
):
    if apply_limited(_client_ip(request)):
        return JSONResponse(
            {"message": "Too many applications from this network. Please try again later."},
            status_code=429,
        )
    payload = await file.read() if file is not None else b""
    db = admin_session()
    try:
        return submit_application(
            db,
            llm=request.app.state.llm,
            requisition_code=requisition_code,
            full_name=full_name,
            email=email,
            phone=phone,
            location=location,
            salary_usd=salary_usd,
            start_on=start_on,
            years_experience=years_experience,
            fsp=fsp,
            last_fsp_on=last_fsp_on,
            last_tssci_on=last_tssci_on,
            note=note,
            filename=file.filename if file is not None else "resume.txt",
            data=payload,
        )
    finally:
        db.close()


@router.get("/config")
def public_config() -> dict:
    settings = get_settings()
    return {
        "company_name": settings.company_name,
        "careers_url": settings.careers_url,
        "tagline": settings.brand_tagline,
        "accent": settings.brand_accent,
        "logo_url": settings.brand_logo_url,
        "hero_url": settings.brand_hero_url,
        "footer": settings.brand_footer,
        "examples": [item.strip() for item in settings.chat_examples.split("|") if item.strip()],
    }


@router.post("/chat")
def chat(body: ChatIn, request: Request):
    # Refusal is decided before any database call.
    if is_refusal(body.message):
        return {"refusal": True, "answer": REFUSAL_TEXT, "jobs": [], "prior_codes": []}
    if _limited(_client_ip(request)):
        return JSONResponse(
            {"message": "Too many questions from this network. Please try again later.", "limited": True, "jobs": []},
            status_code=429,
        )
    db = public_session()
    try:
        try:
            result = search_jobs(db, body.message, body.prior_codes, embedder=request.app.state.embedder)
        except SQLAlchemyError:
            return JSONResponse(
                {
                    "error": "database",
                    "message": "The job database is unavailable right now.",
                    "jobs": [],
                },
                status_code=503,
            )
        if result.no_jobs_loaded:
            return {
                "refusal": False,
                "notice": "Job list has not been loaded yet.",
                "answer": "",
                "jobs": [],
                "prior_codes": [],
            }
        cards = [_card(hit) for hit in result.hits]
        closed = [_card(hit, closed=True) for hit in result.closed_hits]
        codes = [card["requisition_code"] for card in cards]
        notice = None
        answer = ""
        explain_pending = False
        if not cards and closed:
            answer = "No open role requires that. Closed postings that name it are listed below."
        elif not cards:
            answer = "No open jobs matched that search."
        elif result.parsed and (result.parsed.ask_clearance or result.parsed.ask_posting_fact):
            answer = _quote_only(result)
        elif not body.explain:
            answer = _plain_answer(result)
            explain_pending = True
        else:
            try:
                answer = _explain(request, result, body.message, _history_text(body.history))
                answer = drop_unknown_codes(answer, set(codes))
            except LLMError as exc:
                logger.warning("public chat explanation failed: %s", exc)
                notice = "Explanations are unavailable right now."
                answer = ""
        return {
            "refusal": False,
            "notice": notice,
            "answer": answer,
            "explain_pending": explain_pending,
            "jobs": cards,
            "closed_jobs": closed,
            "prior_codes": codes[:24],
        }
    finally:
        db.close()


@router.post("/explain")
def explain(body: ExplainIn, request: Request):
    """The paragraph for cards already shown. Re-runs the same search so only those jobs are described."""
    if is_refusal(body.message):
        return {"answer": REFUSAL_TEXT, "notice": None}
    if _limited(f"explain:{_client_ip(request)}"):
        return JSONResponse({"answer": "", "notice": "Explanations are paused for this network. Please try again later."}, status_code=429)
    db = public_session()
    try:
        try:
            result = search_jobs(db, body.message, body.prior_codes, embedder=request.app.state.embedder)
        except SQLAlchemyError:
            return JSONResponse({"answer": "", "notice": "Explanations are unavailable right now."}, status_code=503)
        wanted = set(body.codes)
        result.hits = [hit for hit in result.hits if hit.job.requisition_code in wanted]
        if not result.hits:
            return {"answer": "", "notice": None}
        try:
            answer = drop_unknown_codes(_explain(request, result, body.message, _history_text(body.history)), wanted)
        except LLMError as exc:
            logger.warning("public explanation failed: %s", exc)
            return {"answer": "", "notice": "Explanations are unavailable right now."}
        return {"answer": answer, "notice": None}
    finally:
        db.close()


def _card(hit, closed: bool = False) -> dict:
    job = hit.job
    on_file = bool((job.description_text or "").strip() or (hit.evidence or "").strip())
    quote = (hit.evidence or "").strip()
    if not quote and on_file:
        paragraphs = [part.strip() for part in (job.description_text or "").split("\n\n") if part.strip()]
        quote = (paragraphs[0] if paragraphs else job.description_text)[:500]
    else:
        quote = quote[:500]
    return {
        "requisition_code": job.requisition_code,
        "title": job.title,
        "location": job.location,
        "matched_skills": hit.matched_skills,
        "confidence": "low" if not on_file else "standard",
        "description_on_file": on_file,
        "description_note": None if on_file else "Full description not on file.",
        "quote": quote,
        "source_url": job.source_url,
        "distance_miles": None if hit.distance_miles is None else round(hit.distance_miles, 1),
        "near_place": hit.near_place,
        "closed": closed,
    }


def _plain_answer(result) -> str:
    hits = result.hits
    closed = result.closed_hits
    if not hits and closed:
        return "No open role requires that. Closed postings that name it are listed below."
    if not hits:
        return "No open jobs matched that search."
    parsed = result.parsed
    if parsed and parsed.near_place:
        if parsed.near_miles is not None:
            miles = int(parsed.near_miles) if parsed.near_miles == int(parsed.near_miles) else parsed.near_miles
            where = f"within {miles} miles of {parsed.near_place}"
        else:
            where = f"closest to {parsed.near_place}"
        if len(hits) == 1:
            job = hits[0].job
            city = f" in {job.location}" if job.location else ""
            return f"{job.requisition_code}, {job.title}{city}, is the open role {where}."
        names = ", ".join(hit.job.requisition_code for hit in hits)
        return f"{len(hits)} open roles are {where}: {names}."
    if len(hits) == 1:
        job = hits[0].job
        where = f" in {job.location}" if job.location else ""
        return f"{job.requisition_code}, {job.title}{where}, is the open role. The matching line from the posting is on the card."
    names = ", ".join(hit.job.requisition_code for hit in hits)
    return f"{len(hits)} open roles match: {names}. Each card quotes the line from the posting."


def _quote_only(result) -> str:
    parsed = result.parsed
    snippets = []
    pattern = r"(?i)[^.]*\b(clearance|polygraph|ts/sci|salary|benefit|citizen|visa|sponsor)\b[^.]*\.?"
    for hit in result.hits:
        text = hit.job.description_text or ""
        found = re.search(pattern, text)
        if found:
            snippets.append(f"{hit.job.requisition_code}: {found.group(0).strip()}")
    if snippets and parsed and parsed.ask_clearance:
        return " ".join(snippets[:4])
    if snippets and parsed and parsed.ask_posting_fact and not parsed.ask_clearance:
        return " ".join(snippets[:4])
    return "That is not in the posting we have on file."


def _history_text(history: list[HistoryTurn]) -> str:
    lines = []
    for turn in history[-6:]:
        who = "Visitor" if turn.role == "user" else "Assistant"
        lines.append(f"{who}: {turn.content.strip()[:500]}")
    return "\n".join(lines)


def _explain(request, result, message: str, history: str = "") -> str:
    payload = []
    for hit in result.hits:
        job = hit.job
        payload.append(
            {
                "requisition_code": job.requisition_code,
                "title": job.title,
                "location": job.location,
                "distance_miles": None if hit.distance_miles is None else round(hit.distance_miles, 1),
                "skills": hit.matched_skills,
                "quote": (hit.evidence or "").strip()
                or _public_quote(
                    job.description_text or "",
                    allow_clearance=bool(result.parsed and result.parsed.ask_clearance),
                    limit=2500,
                ),
            }
        )
    system = (
        "You answer a visitor's question about open job postings already retrieved. "
        "Write 2 to 4 sentences. Use only the requisition codes and quotes provided. "
        "The quote is the posting line that matched. If it names a related tool, such as Spring Framework for a Spring Boot question, say the words the posting uses. "
        "If the quotes do not state what was asked, say that it is not in these postings. "
        "If the question excludes a city, name every city in the retrieved jobs and do not name the excluded city. "
        "If distance_miles is present, use that number and do not invent a different distance. "
        "Do not invent job ids, skills, salary, sponsorship, or candidate information. "
        "Do not mention clearance unless the visitor asked about it."
    )
    cities = sorted({hit.job.location for hit in result.hits if hit.job.location})
    earlier = f"Earlier conversation:\n{history}\n" if history else ""
    user = f"{earlier}Question: {message}\nCities in these jobs: {cities}\nRetrieved jobs:\n{payload}"
    raw = request.app.state.llm.complete(system=system, user=user, temperature=0.2, json_mode=False)
    text = (raw or "").strip()
    if text.startswith("{"):
        try:
            text = parse_json_content(text).get("answer", text)
        except (LLMError, ValueError, TypeError):
            pass
    return text


def _public_quote(description: str, allow_clearance: bool, limit: int = 1200) -> str:
    if allow_clearance:
        return description[:limit]
    kept = []
    for line in description.splitlines():
        if re.search(r"(?i)clearance|polygraph|top secret|ts/sci", line):
            continue
        kept.append(line)
    return "\n".join(kept)[:limit]
