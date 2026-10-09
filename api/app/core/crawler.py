"""Careers crawler: listing page, every linked detail page, and the sanity guard."""

from datetime import datetime, timezone
import hashlib
import logging

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.detail_parser import parse_detail_html
from app.core.embed import Embedder, cosine
from app.core.listing_parser import parse_listing_html
from app.core.llm import LLMClient
from app.core.redact import redact_ssn
from app.core.structure import structure_job
from app.core.tokens import chunk_text, job_vector_text
from app.models import CrawlState, Job, JobChunk

logger = logging.getLogger(__name__)

USER_AGENT = "TalentChat/1.0 (Janus Soft recruiting assistant; +https://www.janus-soft.com/career)"


class CrawlFetchError(Exception):
    pass


class HttpFetcher:
    def __init__(self, timeout: float = 20.0, delay_seconds: float = 1.0) -> None:
        self.timeout = timeout
        self.delay_seconds = delay_seconds
        self._last = 0.0
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )

    def fetch(self, url: str) -> str:
        import time

        now = time.monotonic()
        wait = self.delay_seconds - (now - self._last)
        if self._last and wait > 0:
            time.sleep(wait)
        try:
            response = self._client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise CrawlFetchError(str(exc)) from exc
        finally:
            self._last = time.monotonic()
        return response.text


class MapFetcher:
    """Test double. Keys are exact URLs."""

    def __init__(self, pages: dict[str, str], fail: set[str] | None = None, error: Exception | None = None) -> None:
        self.pages = pages
        self.fail = fail or set()
        self.error = error

    def fetch(self, url: str) -> str:
        if self.error is not None and (not self.fail or url in self.fail):
            raise CrawlFetchError(str(self.error))
        if url in self.fail:
            raise CrawlFetchError(f"failed to fetch {url}")
        if url not in self.pages:
            raise CrawlFetchError(f"missing {url}")
        return self.pages[url]


def description_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _state(session: Session) -> CrawlState:
    state = session.get(CrawlState, 1)
    if state is None:
        state = CrawlState(id=1)
        session.add(state)
        session.flush()
    return state


def _embed_job(session: Session, job: Job, embedder: Embedder) -> None:
    session.query(JobChunk).filter(JobChunk.job_id == job.id).delete()
    chunks = chunk_text(job.description_text or "")
    vectors = embedder.embed_documents(chunks) if chunks else []
    for index, (text, vector) in enumerate(zip(chunks, vectors)):
        session.add(JobChunk(job_id=job.id, ord=index, text=text, embedding=vector))
    vector_text = job_vector_text(job.title or "", job.location or "", job.summary or "", job.description_text or "")
    whole = embedder.embed_documents([vector_text])
    job.embedding = whole[0] if whole else None


def run_crawl(
    session: Session,
    fetcher,
    careers_url: str,
    llm: LLMClient,
    embedder: Embedder,
) -> CrawlState:
    now = datetime.now(timezone.utc)
    state = _state(session)
    state.last_started_at = now
    try:
        html = fetcher.fetch(careers_url)
    except Exception as exc:
        state.last_ok = False
        state.last_error = f"Listing fetch failed: {exc}"
        state.last_finished_at = datetime.now(timezone.utc)
        session.commit()
        logger.warning("crawl listing fetch failed: %s", exc)
        return state

    rows = [row for row in parse_listing_html(html) if row.requisition_code]
    open_count = session.scalar(select(func.count()).select_from(Job).where(Job.status == "open")) or 0
    if len(rows) == 0 or (open_count and len(rows) < 0.5 * open_count):
        if len(rows) == 0:
            message = "Crawl sanity guard: listing parsed to 0 rows. No jobs were changed."
        else:
            message = (
                f"Crawl sanity guard: listing parsed to {len(rows)} rows, "
                f"fewer than half of {open_count} open jobs. No jobs were changed."
            )
        state.last_ok = False
        state.last_error = message
        state.last_rows = len(rows)
        state.last_finished_at = datetime.now(timezone.utc)
        session.commit()
        return state

    seen: set[str] = set()
    for row in rows:
        seen.add(row.requisition_code)
        job = session.scalar(select(Job).where(Job.requisition_code == row.requisition_code))
        if job is None:
            job = Job(requisition_code=row.requisition_code)
            session.add(job)
        job.title = row.title
        job.location = row.location
        job.program_tag = row.program_tag
        job.external_req = row.external_req
        if not job.closed_manually:
            job.status = row.status
            if job.status != "closed":
                job.close_note = None
        job.source_line = row.source_line
        job.site_job_id = row.site_job_id
        job.source_url = row.source_url
        job.last_seen_at = now
        job.needs_review = row.needs_review
        detail_url = row.source_url
        if not detail_url:
            job.needs_review = True
            job.detail_error = "Listing line had no detail link."
            continue
        try:
            detail_html = fetcher.fetch(detail_url)
        except Exception as exc:
            job.needs_review = True
            job.detail_error = f"Detail fetch failed: {exc}"
            logger.warning("detail fetch failed for %s: %s", row.requisition_code, exc)
            continue
        job.detail_error = None
        parsed = parse_detail_html(detail_html)
        if parsed.needs_review:
            job.needs_review = True
        text = redact_ssn(parsed.description_text or "")
        digest = description_hash(text) if text else None
        posting = redact_ssn(parsed.posting_text or text)
        if posting:
            job.careers_description_text = posting
            job.careers_description_hash = description_hash(posting)
        if job.description_source == "admin":
            continue
        if text and digest == job.description_hash and job.description_text:
            job.description_source = job.description_source or "careers_page"
            continue
        if not text:
            if not job.description_text:
                job.description_source = "none"
            job.needs_review = True
            continue
        structured = structure_job(parsed, llm)
        job.description_text = structured["description_text"]
        job.description_source = "careers_page"
        job.description_hash = description_hash(job.description_text)
        job.must_have_skills = structured["must_have_skills"]
        job.nice_to_have_skills = structured["nice_to_have_skills"]
        job.clearance_required = structured["clearance_required"]
        job.polygraph_required = structured["polygraph_required"]
        job.summary = structured["summary"]
        job.skill_quotes = structured["skill_quotes"]
        job.needs_review = job.needs_review or structured["needs_review"]
        try:
            _embed_job(session, job, embedder)
        except Exception:
            logger.exception("embedding failed for %s", job.requisition_code)

    for job in session.scalars(select(Job)).all():
        if job.requisition_code not in seen and job.status != "closed":
            job.status = "closed"
            if not (job.close_note or "").strip():
                job.close_note = "No longer listed on the careers page."
    state.last_ok = True
    state.last_error = None
    state.last_rows = len(rows)
    state.last_finished_at = datetime.now(timezone.utc)
    session.commit()
    return state


def replaced_cosine(left, right) -> float:
    return cosine(left, right)
