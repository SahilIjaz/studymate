"""FastAPI application factory."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import Services
from app.api.routes import chat, documents, health
from app.config import Settings, get_settings
from app.core.rate_limit import TokenBucketLimiter
from app.errors import UnauthorizedError, install_exception_handlers
from app.logging_config import (
    configure_logging,
    get_logger,
    reset_request_id,
    set_request_id,
)
from app.services.embeddings import build_embedder
from app.services.gemini import GeminiService
from app.services.index import IndexRegistry
from app.services.ingestion import IngestionService
from app.services.llm import ClaudeService, LLMService, MockClaudeService
from app.storage.db import Database

log = get_logger(__name__)

_OPEN_PATHS = ("/health", "/docs", "/redoc", "/openapi.json")


def build_services(settings: Settings) -> Services:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.workspaces_dir.mkdir(parents=True, exist_ok=True)
    db = Database(settings.database_path)
    embedder = build_embedder(settings)
    registry = IndexRegistry(settings.workspaces_dir, embedder, db)
    return Services(
        settings=settings,
        db=db,
        embedder=embedder,
        registry=registry,
        ingestion=IngestionService(db=db, registry=registry, embedder=embedder, settings=settings),
        claude=build_llm(settings),
        ask_limiter=TokenBucketLimiter(
            capacity=settings.rate_limit_ask_per_minute,
            refill_per_minute=settings.rate_limit_ask_per_minute,
        ),
        upload_limiter=TokenBucketLimiter(
            capacity=settings.rate_limit_upload_per_minute,
            refill_per_minute=settings.rate_limit_upload_per_minute,
        ),
        started_at=time.time(),
    )


def build_llm(settings: Settings) -> LLMService:
    provider = settings.resolved_llm_provider
    if provider == "gemini":
        return GeminiService(settings)
    if provider == "mock":
        return MockClaudeService(settings)
    return ClaudeService(settings)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        services = build_services(settings)
        app.state.services = services
        log.info(
            "startup",
            extra={
                "version": settings.app_version,
                "llm": f"{services.claude.provider}:{services.claude.model}",
                "embedder": services.embedder.name,
                "llm_configured": services.claude.configured,
            },
        )
        try:
            yield
        finally:
            services.db.close()
            log.info("shutdown")

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Ask questions about your own PDFs. Hybrid retrieval over FAISS + BM25, answers streamed from Claude with page-level citations.",
        lifespan=lifespan,
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Workspace-Id", "X-API-Key", "X-Request-Id"],
        expose_headers=["X-Request-Id", "Retry-After"],
        max_age=600,
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        token = set_request_id(request_id)
        started = time.perf_counter()
        try:
            if (
                settings.app_api_key
                and not request.url.path.startswith(_OPEN_PATHS)
                and request.method != "OPTIONS"
                and request.headers.get("x-api-key") != settings.app_api_key
            ):
                exc = UnauthorizedError("Invalid or missing API key.", code="invalid_api_key")
                return Response(
                    content=json.dumps(exc.to_payload()), status_code=401, media_type="application/json"
                )
            response = await call_next(request)
        finally:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
            reset_request_id(token)
        response.headers["X-Request-Id"] = request_id
        if not request.url.path.startswith("/health"):
            log.info(
                "request",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "ms": elapsed_ms,
                },
            )
        return response

    install_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(documents.router)
    app.include_router(chat.router)
    return app


app = create_app()
