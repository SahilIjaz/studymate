from __future__ import annotations

import time

from fastapi import APIRouter

from app.api.deps import ServicesDep
from app.schemas import HealthOut

router = APIRouter(tags=["health"])


@router.get("/", include_in_schema=False)
async def root(services: ServicesDep) -> dict[str, str]:
    """Hosting platforms probe `/`; point humans at the docs."""
    return {
        "service": services.settings.app_name,
        "version": services.settings.app_version,
        "docs": "/docs",
        "health": "/health",
    }


@router.get("/health", response_model=HealthOut)
async def health(services: ServicesDep) -> HealthOut:
    s = services.settings
    return HealthOut(
        status="ok",
        version=s.app_version,
        environment=s.environment,
        llm_provider=services.claude.provider,
        model=services.claude.model,
        fast_model=services.claude.fast_model,
        embedding_provider=services.embedder.name,
        embedding_dimension=services.embedder.dimension,
        llm_configured=services.claude.configured,
        uptime_seconds=round(time.time() - services.started_at, 1),
    )


@router.get("/health/ready")
async def ready(services: ServicesDep) -> dict[str, str]:
    with services.db.connection() as conn:
        conn.execute("SELECT 1").fetchone()
    return {"status": "ready"}
