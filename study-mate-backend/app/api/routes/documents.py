from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile, status

from app.api.deps import ServicesDep, WorkspaceDep, rate_limit_upload
from app.errors import NotFoundError, ValidationError
from app.schemas import DocumentListOut, DocumentOut, SuggestionsOut, UploadOut

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=DocumentListOut)
async def list_documents(services: ServicesDep, workspace_id: WorkspaceDep) -> DocumentListOut:
    rows = await asyncio.to_thread(services.db.list_documents, workspace_id)
    return DocumentListOut(
        documents=[DocumentOut.from_row(r) for r in rows],
        limit=services.settings.max_docs_per_workspace,
    )


@router.post(
    "",
    response_model=UploadOut,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit_upload)],
)
async def upload_document(
    services: ServicesDep,
    workspace_id: WorkspaceDep,
    background: BackgroundTasks,
    file: Annotated[UploadFile, File()],
) -> UploadOut:
    doc, created = await services.ingestion.accept(workspace_id, file)
    if created:
        background.add_task(services.ingestion.process, workspace_id, doc.id)
    return UploadOut(document=DocumentOut.from_row(doc), already_indexed=not created)


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(services: ServicesDep, workspace_id: WorkspaceDep, document_id: str) -> DocumentOut:
    row = await asyncio.to_thread(services.db.get_document, workspace_id, document_id)
    if row is None:
        raise NotFoundError("Document not found.", code="document_not_found")
    return DocumentOut.from_row(row)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(services: ServicesDep, workspace_id: WorkspaceDep, document_id: str) -> None:
    await asyncio.to_thread(services.ingestion.delete, workspace_id, document_id)


@router.get("/{document_id}/suggestions", response_model=SuggestionsOut)
async def suggest_questions(
    services: ServicesDep, workspace_id: WorkspaceDep, document_id: str
) -> SuggestionsOut:
    row = await asyncio.to_thread(services.db.get_document, workspace_id, document_id)
    if row is None:
        raise NotFoundError("Document not found.", code="document_not_found")
    if row.status != "ready":
        raise ValidationError("The document is still being indexed.", code="document_not_ready")
    chunks = await asyncio.to_thread(services.db.first_chunks, workspace_id, document_id, 6)
    excerpt = "\n\n".join(c.text for c in chunks)
    questions = await services.claude.suggest_questions(excerpt)
    return SuggestionsOut(questions=questions)
