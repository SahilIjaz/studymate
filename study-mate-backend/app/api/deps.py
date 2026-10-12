"""Request-scoped dependencies: app services, workspace identity, limits."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request

from app.config import Settings
from app.core.ids import is_workspace_id
from app.core.rate_limit import TokenBucketLimiter
from app.errors import RateLimitedError, ValidationError
from app.services.embeddings import Embedder
from app.services.index import IndexRegistry
from app.services.ingestion import IngestionService
from app.services.llm import LLMService
from app.storage.db import Database


@dataclass(slots=True)
class Services:
    settings: Settings
    db: Database
    embedder: Embedder
    registry: IndexRegistry
    ingestion: IngestionService
    claude: LLMService
    ask_limiter: TokenBucketLimiter
    upload_limiter: TokenBucketLimiter
    started_at: float


def get_services(request: Request) -> Services:
    return request.app.state.services


ServicesDep = Annotated[Services, Depends(get_services)]


def get_workspace_id(
    x_workspace_id: Annotated[str | None, Header(alias="X-Workspace-Id")] = None,
) -> str:
    """Workspaces are opaque UUIDs minted by the client and sent on every call.

    A UUID is unguessable enough to keep casual users apart in a demo. It is
    not authentication; put a real identity provider here for multi-tenant use.
    """
    if not x_workspace_id or not is_workspace_id(x_workspace_id):
        raise ValidationError(
            "Missing or malformed X-Workspace-Id header (expected a UUID).",
            code="workspace_required",
        )
    return x_workspace_id.lower()


WorkspaceDep = Annotated[str, Depends(get_workspace_id)]


def _client_key(request: Request, workspace_id: str) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    ip = (
        forwarded.split(",")[0].strip()
        if forwarded
        else (request.client.host if request.client else "unknown")
    )
    return f"{workspace_id}:{ip}"


def rate_limit_ask(request: Request, services: ServicesDep, workspace_id: WorkspaceDep) -> None:
    _enforce(services.ask_limiter, _client_key(request, workspace_id), "questions")


def rate_limit_upload(request: Request, services: ServicesDep, workspace_id: WorkspaceDep) -> None:
    _enforce(services.upload_limiter, _client_key(request, workspace_id), "uploads")


def _enforce(limiter: TokenBucketLimiter, key: str, what: str) -> None:
    allowed, wait = limiter.try_acquire(key)
    if not allowed:
        seconds = max(1, int(wait + 0.999))
        raise RateLimitedError(
            f"Too many {what}. Try again in {seconds}s.",
            headers={"Retry-After": str(seconds)},
            details={"retry_after_seconds": seconds},
        )
