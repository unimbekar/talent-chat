"""Public HTTP routes. No candidate reads."""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import logging
import re
import threading

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.core.llm import LLMError, parse_json_content
from app.db import public_session
from app.public.refusal import REFUSAL_TEXT, is_refusal
from app.public.search import drop_unknown_codes, search_jobs

router = APIRouter(prefix="/public", tags=["public"])
logger = logging.getLogger("talent")

_LOCK = threading.Lock()
_HITS: dict[str, list[datetime]] = defaultdict(list)
_LIMIT = 30


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    prior_codes: list[str] = Field(default_factory=list)


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


@router.get("/config")
def public_config() -> dict:
    settings = get_settings()
    return {"company_name": settings.company_name, "careers_url": settings.careers_url}


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
        codes = [card["requisition_code"] for card in cards]
        notice = None
        answer = ""
        if not cards:
            answer = "No open jobs matched that search."
        elif result.parsed and (result.parsed.ask_clearance or result.parsed.ask_posting_fact):
            answer = _quote_only(result)
        else:
            try:
                answer = _explain(request, result, body.message)
                answer = drop_unknown_codes(answer, set(codes))
            except LLMError as exc:
                logger.warning("public chat explanation failed: %s", exc)
                notice = "Explanations are unavailable right now."
                answer = ""
        return {
            "refusal": False,
            "notice": notice,
            "answer": answer,
            "jobs": cards,
            "prior_codes": codes[:24],
        }
    finally:
        db.close()


def _card(hit) -> dict:
    job = hit.job
    on_file = bool((job.description_text or "").strip())
    quote = ""
    if on_file:
        paragraphs = [part.strip() for part in (job.description_text or "").split("\n\n") if part.strip()]
        quote = (paragraphs[0] if paragraphs else job.description_text)[:500]
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
    }


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


def _explain(request, result, message: str) -> str:
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
                "quote": _public_quote(
                    job.description_text or "",
                    allow_clearance=bool(result.parsed and result.parsed.ask_clearance),
                    limit=2500,
                ),
            }
        )
    system = (
        "You answer a visitor's question about open job postings already retrieved. "
        "Write 2 to 4 sentences. Use only the requisition codes and quotes provided. "
        "If the quotes do not state what was asked, say that it is not in these postings. "
        "If the question excludes a city, name every city in the retrieved jobs and do not name the excluded city. "
        "If distance_miles is present, use that number and do not invent a different distance. "
        "Do not invent job ids, skills, salary, sponsorship, or candidate information. "
        "Do not mention clearance unless the visitor asked about it."
    )
    cities = sorted({hit.job.location for hit in result.hits if hit.job.location})
    user = f"Question: {message}\nCities in these jobs: {cities}\nRetrieved jobs:\n{payload}"
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
