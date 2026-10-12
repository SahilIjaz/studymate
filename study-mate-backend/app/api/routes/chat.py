"""Question answering with Server-Sent Events.

Event sequence for one question:

    meta     {conversation_id, user_message_id}
    status   {stage: "retrieving" | "thinking"}
    sources  {sources: [Citation...], retrieval_query}
    delta    {text}                      (many)
    done     {message_id, usage, model}
    error    {code, message}             (terminal, replaces `done`)
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse

from app.api.deps import Services, ServicesDep, WorkspaceDep, rate_limit_ask
from app.core.ids import new_id
from app.errors import AppError, NotFoundError, ValidationError
from app.logging_config import get_logger
from app.schemas import (
    AskIn,
    AskOut,
    Citation,
    ConversationDetailOut,
    ConversationListOut,
    ConversationOut,
    CreateConversationIn,
    MessageOut,
)
from app.services.llm import Completed, Delta
from app.services.retrieval import (
    RetrievedChunk,
    is_overview_question,
    overview_chunks,
    retrieve,
)
from app.storage.db import ConversationRow, MessageRow

log = get_logger(__name__)
router = APIRouter(tags=["chat"])

NO_DOCUMENTS_ANSWER = "You haven't uploaded any documents yet. Add a PDF and ask again."
NO_SOURCES_ANSWER = (
    "I couldn't find anything about that in your documents. Try rephrasing with terms the "
    "material uses, or check that the right PDF is uploaded."
)


# --------------------------------------------------------------- conversations
@router.get("/conversations", response_model=ConversationListOut)
async def list_conversations(services: ServicesDep, workspace_id: WorkspaceDep) -> ConversationListOut:
    rows = await asyncio.to_thread(services.db.list_conversations, workspace_id)
    return ConversationListOut(conversations=[ConversationOut.from_row(r) for r in rows])


@router.post(
    "/conversations",
    response_model=ConversationOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    services: ServicesDep, workspace_id: WorkspaceDep, body: CreateConversationIn
) -> ConversationOut:
    row = _new_conversation(services, workspace_id, body.title or "New conversation")
    return ConversationOut.from_row(row)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailOut)
async def get_conversation(
    services: ServicesDep, workspace_id: WorkspaceDep, conversation_id: str
) -> ConversationDetailOut:
    row = await asyncio.to_thread(services.db.get_conversation, workspace_id, conversation_id)
    if row is None:
        raise NotFoundError("Conversation not found.", code="conversation_not_found")
    messages = await asyncio.to_thread(services.db.list_messages, conversation_id)
    return ConversationDetailOut(
        **ConversationOut.from_row(row).model_dump(),
        messages=[MessageOut.from_row(m) for m in messages],
    )


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    services: ServicesDep, workspace_id: WorkspaceDep, conversation_id: str
) -> None:
    deleted = await asyncio.to_thread(services.db.delete_conversation, workspace_id, conversation_id)
    if not deleted:
        raise NotFoundError("Conversation not found.", code="conversation_not_found")


# ------------------------------------------------------------------------ ask
@router.post("/chat/stream", dependencies=[Depends(rate_limit_ask)])
async def ask_stream(services: ServicesDep, workspace_id: WorkspaceDep, body: AskIn) -> StreamingResponse:
    _validate_question(services, body)

    async def event_source() -> AsyncIterator[bytes]:
        async for name, payload in _answer(services, workspace_id, body):
            yield _sse(name, payload)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/chat/ask", response_model=AskOut, dependencies=[Depends(rate_limit_ask)])
async def ask(services: ServicesDep, workspace_id: WorkspaceDep, body: AskIn) -> AskOut:
    """Non-streaming variant for scripts and tests."""
    _validate_question(services, body)
    conversation_id = ""
    text_parts: list[str] = []
    citations: list[dict[str, Any]] = []
    retrieval_query = body.question
    done: dict[str, Any] = {}
    async for name, payload in _answer(services, workspace_id, body):
        if name == "meta":
            conversation_id = payload["conversation_id"]
        elif name == "sources":
            citations = payload["sources"]
            retrieval_query = payload["retrieval_query"]
        elif name == "delta":
            text_parts.append(payload["text"])
        elif name == "done":
            done = payload
        elif name == "error":
            raise AppError(
                payload["message"],
                code=payload["code"],
                status_code=payload.get("status", 502),
            )
    return AskOut(
        conversation_id=conversation_id,
        retrieval_query=retrieval_query,
        message=MessageOut(
            id=done["message_id"],
            role="assistant",
            content="".join(text_parts),
            citations=[Citation(**c) for c in citations],
            usage=done.get("usage"),
            created_at=time.time(),
        ),
    )


# ------------------------------------------------------------------ pipeline
def _validate_question(services: Services, body: AskIn) -> None:
    if not body.question.strip():
        raise ValidationError("Question cannot be empty.", code="empty_question")
    if len(body.question) > services.settings.max_question_chars:
        raise ValidationError(
            f"Questions are limited to {services.settings.max_question_chars} characters.",
            code="question_too_long",
        )


def _new_conversation(services: Services, workspace_id: str, title: str) -> ConversationRow:
    now = time.time()
    row = ConversationRow(
        id=new_id("conv"),
        workspace_id=workspace_id,
        title=title[:120],
        created_at=now,
        updated_at=now,
    )
    services.db.insert_conversation(row)
    return row


def _title_from(question: str) -> str:
    cleaned = " ".join(question.split())
    return cleaned if len(cleaned) <= 60 else cleaned[:57].rstrip() + "..."


def _citation(n: int, item: RetrievedChunk) -> dict[str, Any]:
    c = item.chunk
    return {
        "n": n,
        "chunk_id": c.id,
        "document_id": c.document_id,
        "filename": item.filename,
        "page_start": c.page_start,
        "page_end": c.page_end,
        "score": item.score,
        "text": c.text,
    }


async def _answer(
    services: Services, workspace_id: str, body: AskIn
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    db = services.db
    question = body.question.strip()

    # 1. Conversation + history --------------------------------------------
    if body.conversation_id:
        convo = db.get_conversation(workspace_id, body.conversation_id)
        if convo is None:
            yield (
                "error",
                {
                    "code": "conversation_not_found",
                    "message": "Conversation not found.",
                    "status": 404,
                },
            )
            return
        is_first = False
    else:
        convo = _new_conversation(services, workspace_id, _title_from(question))
        is_first = True

    prior = db.list_messages(convo.id, limit=services.settings.history_turns * 2)
    history = [(m.role, m.content) for m in prior if m.status == "complete"]

    user_msg = MessageRow(
        id=new_id("msg"),
        conversation_id=convo.id,
        role="user",
        content=question,
        created_at=time.time(),
    )
    db.insert_message(user_msg)
    if is_first:
        db.touch_conversation(convo.id, title=_title_from(question))
    else:
        db.touch_conversation(convo.id)

    yield "meta", {"conversation_id": convo.id, "user_message_id": user_msg.id}
    yield "status", {"stage": "retrieving"}

    # 2. Retrieval -------------------------------------------------------------
    documents = db.list_documents(workspace_id)
    ready_docs = {d.id: d for d in documents if d.status == "ready"}
    if not ready_docs:
        async for event in _canned(services, convo.id, NO_DOCUMENTS_ANSWER, question):
            yield event
        return

    retrieval_query = question
    if services.settings.query_rewrite and history:
        retrieval_query = await services.claude.condense_question(history, question)

    scope = set(body.document_ids) & set(ready_docs) if body.document_ids else None
    if is_overview_question(retrieval_query):
        targets = sorted(scope or ready_docs, key=lambda d: ready_docs[d].created_at)
        hits = await asyncio.to_thread(overview_chunks, db, workspace_id, targets, services.settings.top_k)
    else:
        index = services.registry.get(workspace_id)
        hits = await asyncio.to_thread(
            retrieve,
            question=retrieval_query,
            index=index,
            embedder=services.embedder,
            db=db,
            settings=services.settings,
            document_ids=scope,
        )
    for hit in hits:
        hit.filename = (
            ready_docs[hit.chunk.document_id].filename if hit.chunk.document_id in ready_docs else "document"
        )

    citations = [_citation(n, h) for n, h in enumerate(hits, start=1)]
    yield "sources", {"sources": citations, "retrieval_query": retrieval_query}

    if not hits:
        async for event in _canned(services, convo.id, NO_SOURCES_ANSWER, question):
            yield event
        return

    # 3. Generation ------------------------------------------------------------
    yield "status", {"stage": "thinking"}
    assistant_id = new_id("msg")
    parts: list[str] = []
    completed: Completed | None = None
    try:
        async for event in services.claude.stream_answer(question=question, sources=hits, history=history):
            if isinstance(event, Delta):
                parts.append(event.text)
                yield "delta", {"text": event.text}
            elif isinstance(event, Completed):
                completed = event
    except AppError as exc:
        _persist(
            services,
            assistant_id,
            convo.id,
            "".join(parts),
            citations,
            None,
            status="failed",
        )
        yield (
            "error",
            {"code": exc.code, "message": exc.message, "status": exc.status_code},
        )
        return
    except (asyncio.CancelledError, GeneratorExit):
        # Client went away mid-stream. Keep what was generated so the
        # conversation isn't left with an orphaned question.
        _persist(
            services,
            assistant_id,
            convo.id,
            "".join(parts),
            citations,
            None,
            status="interrupted",
        )
        raise

    usage = completed.usage if completed else None
    _persist(
        services,
        assistant_id,
        convo.id,
        "".join(parts),
        citations,
        usage,
        status="complete",
    )
    yield (
        "done",
        {
            "message_id": assistant_id,
            "conversation_id": convo.id,
            "usage": usage,
            "model": completed.model if completed else services.settings.claude_model,
        },
    )


async def _canned(
    services: Services, conversation_id: str, answer: str, question: str
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    message_id = new_id("msg")
    yield "sources", {"sources": [], "retrieval_query": question}
    yield "delta", {"text": answer}
    _persist(services, message_id, conversation_id, answer, [], None, status="complete")
    yield (
        "done",
        {
            "message_id": message_id,
            "conversation_id": conversation_id,
            "usage": None,
            "model": None,
        },
    )


def _persist(
    services: Services,
    message_id: str,
    conversation_id: str,
    content: str,
    citations: list[dict[str, Any]],
    usage: dict[str, Any] | None,
    *,
    status: str,
) -> None:
    services.db.insert_message(
        MessageRow(
            id=message_id,
            conversation_id=conversation_id,
            role="assistant",
            content=content,
            citations=citations,
            usage=usage,
            status=status,
            created_at=time.time(),
        )
    )
    services.db.touch_conversation(conversation_id)


def _sse(event: str, payload: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()
