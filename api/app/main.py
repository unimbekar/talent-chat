"""API entrypoint. Crawl timer lives in this process for Phase 1."""

import asyncio
import logging
from contextlib import asynccontextmanager
import threading
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.admin.assistant.routes import router as assistant_router
from app.admin.benefits_routes import public_router as public_benefits_router
from app.admin.benefits_routes import router as benefits_router
from app.admin.pipeline import router as pipeline_router
from app.admin.push_routes import router as push_router
from app.admin.reports import router as reports_router
from app.admin.routes import router as admin_router
from app.admin.settings_routes import router as settings_router
from app.config import get_settings
from app.core.crawler import HttpFetcher, run_crawl
from app.core.embed import FastEmbedder
from app.core.llm import build_llm_client
from app.db import admin_session
from app.knowledge.routes import router as knowledge_router
from app.public.routes import router as public_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("talent")


def _saved_model_names() -> tuple[str, str]:
    """Chat and assistant tags saved in settings. Empty strings mean use the environment."""
    from app.desk_settings import saved_assistant_model, saved_chat_model

    session = admin_session()
    try:
        return saved_chat_model(session), saved_assistant_model(session)
    finally:
        session.close()


def _crawl_once() -> None:
    settings = get_settings()
    session = admin_session()
    try:
        try:
            from app.desk_settings import resolved_chat_model

            model = resolved_chat_model(session, settings.llm_model)
        except Exception:
            logger.exception("saved chat model unavailable; crawl uses the environment model")
            model = settings.llm_model
        fetcher = HttpFetcher(timeout=20, delay_seconds=settings.crawl_request_delay_seconds)
        run_crawl(
            session,
            fetcher,
            settings.careers_url,
            llm=build_llm_client(
                settings.llm_backend,
                settings.llm_base_url,
                model,
                settings.llm_api_key,
                settings.aws_region,
            ),
            embedder=FastEmbedder(settings.embedding_model),
        )
    finally:
        session.close()


def _warm_resume_cache() -> None:
    """Read every résumé once so the first job page after a restart is not slow."""
    from sqlalchemy import select

    from app.core.structure import resume_facts
    from app.models import Candidate

    session = admin_session()
    try:
        for text in session.scalars(select(Candidate.redacted_text)).all():
            resume_facts(text or "")
    finally:
        session.close()


def _rechunk_knowledge(embedder) -> None:
    """Documents saved before sections existed are split again by heading."""
    from app.knowledge.store import rechunk_stale

    session = admin_session()
    try:
        count = rechunk_stale(session, embedder)
        if count:
            logger.info("knowledge base: split %s document(s) into sections", count)
    except Exception:
        logger.exception("knowledge base re-split failed")
        session.rollback()
    finally:
        session.close()


async def _crawl_loop() -> None:
    settings = get_settings()
    while True:
        try:
            await asyncio.to_thread(_crawl_once)
        except Exception:
            logger.exception("scheduled crawl failed")
        await asyncio.sleep(max(settings.crawl_interval_hours, 1) * 3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.llm_backend == "bedrock" and not settings.s3_bucket.strip():
        logger.warning("S3_BUCKET is empty while LLM_BACKEND=bedrock; résumé files stay on container disk")
    chat_model = settings.llm_model
    assistant_model = settings.assistant_model.strip()
    try:
        saved_chat, saved_assistant = _saved_model_names()
        if saved_chat:
            chat_model = saved_chat
        if saved_assistant:
            assistant_model = saved_assistant
    except Exception:
        logger.exception("saved model settings unavailable; starting with the environment model")
    app.state.llm = build_llm_client(
        settings.llm_backend,
        settings.llm_base_url,
        chat_model,
        settings.llm_api_key,
        settings.aws_region,
    )
    app.state.running_model = chat_model
    if assistant_model and assistant_model != chat_model:
        backend = settings.assistant_backend.strip() or settings.llm_backend
        app.state.assistant_llm = build_llm_client(
            backend,
            settings.llm_base_url,
            assistant_model,
            settings.llm_api_key,
            settings.aws_region,
        )
    app.state.running_assistant_model = assistant_model or chat_model
    app.state.embedder = FastEmbedder(settings.embedding_model)
    threading.Thread(target=_rechunk_knowledge, args=(app.state.embedder,), name="knowledge-sections", daemon=True).start()
    if settings.warm_resume_cache:
        threading.Thread(target=_warm_resume_cache, name="warm-resume-cache", daemon=True).start()
    task = None
    if settings.crawl_on_start:
        task = asyncio.create_task(_crawl_loop())
    yield
    if task is not None:
        task.cancel()


def create_app() -> FastAPI:
    app = FastAPI(title=get_settings().company_name, lifespan=lifespan)
    app.include_router(public_router)
    app.include_router(admin_router)
    app.include_router(settings_router)
    app.include_router(pipeline_router)
    app.include_router(push_router)
    app.include_router(reports_router)
    app.include_router(assistant_router)
    app.include_router(knowledge_router)
    app.include_router(benefits_router)
    app.include_router(public_benefits_router)

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        rid = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = rid
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("request failed request_id=%s", rid)
            return JSONResponse({"message": "The service hit an unexpected error."}, status_code=500)
        response.headers["X-Request-ID"] = rid
        return response

    @app.get("/health")
    def health():
        return {"ok": True}

    return app


app = create_app()
