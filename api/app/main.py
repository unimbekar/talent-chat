"""API entrypoint. Crawl timer lives in this process for Phase 1."""

import asyncio
import logging
from contextlib import asynccontextmanager
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.admin.routes import router as admin_router
from app.config import get_settings
from app.core.crawler import HttpFetcher, run_crawl
from app.core.embed import FastEmbedder
from app.core.llm import build_llm_client
from app.db import admin_session
from app.public.routes import router as public_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("talent")


def _crawl_once() -> None:
    settings = get_settings()
    session = admin_session()
    try:
        fetcher = HttpFetcher(timeout=20, delay_seconds=settings.crawl_request_delay_seconds)
        run_crawl(
            session,
            fetcher,
            settings.careers_url,
            llm=build_llm_client(
                settings.llm_backend,
                settings.llm_base_url,
                settings.llm_model,
                settings.llm_api_key,
                settings.aws_region,
            ),
            embedder=FastEmbedder(settings.embedding_model),
        )
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
    app.state.llm = build_llm_client(
        settings.llm_backend,
        settings.llm_base_url,
        settings.llm_model,
        settings.llm_api_key,
        settings.aws_region,
    )
    app.state.embedder = FastEmbedder(settings.embedding_model)
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
