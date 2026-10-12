"""Request and response models for the public API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.storage.db import ConversationRow, DocumentRow, MessageRow

DocumentStatus = Literal["processing", "ready", "failed"]


class DocumentOut(BaseModel):
    id: str
    filename: str
    size_bytes: int
    page_count: int
    chunk_count: int
    status: DocumentStatus
    error: str | None = None
    created_at: float

    @classmethod
    def from_row(cls, row: DocumentRow) -> DocumentOut:
        return cls(
            id=row.id,
            filename=row.filename,
            size_bytes=row.size_bytes,
            page_count=row.page_count,
            chunk_count=row.chunk_count,
            status=row.status,  # type: ignore[arg-type]
            error=row.error,
            created_at=row.created_at,
        )


class DocumentListOut(BaseModel):
    documents: list[DocumentOut]
    limit: int


class UploadOut(BaseModel):
    document: DocumentOut
    already_indexed: bool = False


class SuggestionsOut(BaseModel):
    questions: list[str]


class Citation(BaseModel):
    n: int
    chunk_id: int
    document_id: str
    filename: str
    page_start: int
    page_end: int
    score: float
    text: str


class MessageOut(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    citations: list[Citation] = Field(default_factory=list)
    usage: dict[str, Any] | None = None
    status: str = "complete"
    created_at: float

    @classmethod
    def from_row(cls, row: MessageRow) -> MessageOut:
        return cls(
            id=row.id,
            role=row.role,  # type: ignore[arg-type]
            content=row.content,
            citations=[Citation(**c) for c in row.citations],
            usage=row.usage,
            status=row.status,
            created_at=row.created_at,
        )


class ConversationOut(BaseModel):
    id: str
    title: str
    created_at: float
    updated_at: float

    @classmethod
    def from_row(cls, row: ConversationRow) -> ConversationOut:
        return cls(
            id=row.id,
            title=row.title,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut]


class ConversationListOut(BaseModel):
    conversations: list[ConversationOut]


class CreateConversationIn(BaseModel):
    title: str | None = Field(default=None, max_length=120)


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None
    document_ids: list[str] | None = Field(default=None, max_length=50)


class AskOut(BaseModel):
    conversation_id: str
    message: MessageOut
    retrieval_query: str


class HealthOut(BaseModel):
    status: str
    version: str
    environment: str
    llm_provider: str
    model: str
    fast_model: str
    embedding_provider: str
    embedding_dimension: int
    llm_configured: bool
    uptime_seconds: float
