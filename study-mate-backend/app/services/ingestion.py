"""Document lifecycle: accept an upload, index it in the background, delete it."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from fastapi import UploadFile

from app.config import Settings
from app.core.files import read_upload, sanitize_filename, sha256_hex
from app.core.ids import new_id
from app.errors import AppError, NotFoundError, ValidationError
from app.logging_config import get_logger
from app.services.chunking import chunk_pages
from app.services.embeddings import Embedder, EmbeddingUnavailableError
from app.services.index import IndexRegistry
from app.services.pdf import extract_pages
from app.storage.db import ChunkRow, Database, DocumentRow

log = get_logger(__name__)


class IngestionService:
    def __init__(
        self,
        *,
        db: Database,
        registry: IndexRegistry,
        embedder: Embedder,
        settings: Settings,
    ) -> None:
        self.db = db
        self.registry = registry
        self.embedder = embedder
        self.settings = settings

    def _files_dir(self, workspace_id: str) -> Path:
        path = self.settings.workspaces_dir / workspace_id / "files"
        path.mkdir(parents=True, exist_ok=True)
        return path

    async def accept(self, workspace_id: str, upload: UploadFile) -> tuple[DocumentRow, bool]:
        """Validate and store the upload. Returns (document, created)."""
        if self.db.count_documents(workspace_id) >= self.settings.max_docs_per_workspace:
            raise ValidationError(
                f"This workspace already holds {self.settings.max_docs_per_workspace} documents. Delete one first.",
                code="workspace_full",
            )
        filename = sanitize_filename(upload.filename)
        data = await read_upload(upload, self.settings.max_upload_bytes)
        digest = sha256_hex(data)

        existing = self.db.find_document_by_hash(workspace_id, digest)
        if existing is not None:
            return existing, False

        doc_id = new_id("doc")
        stored = self._files_dir(workspace_id) / f"{doc_id}.pdf"
        await asyncio.to_thread(stored.write_bytes, data)

        now = time.time()
        doc = DocumentRow(
            id=doc_id,
            workspace_id=workspace_id,
            filename=filename,
            stored_path=str(stored),
            sha256=digest,
            size_bytes=len(data),
            page_count=0,
            chunk_count=0,
            status="processing",
            error=None,
            created_at=now,
            updated_at=now,
        )
        self.db.insert_document(doc)
        return doc, True

    def process(self, workspace_id: str, doc_id: str) -> None:
        """Parse, chunk, embed and index. Runs in a worker thread."""
        doc = self.db.get_document(workspace_id, doc_id)
        if doc is None:
            return
        started = time.perf_counter()
        try:
            pages = extract_pages(Path(doc.stored_path), max_pages=self.settings.max_pages)
            chunks = chunk_pages(
                pages,
                chunk_size=self.settings.chunk_size_words,
                overlap=self.settings.chunk_overlap_words,
            )
            if not chunks:
                raise ValidationError("The PDF contained no usable text.", code="no_text_layer")

            rows = [
                ChunkRow(
                    id=0,
                    workspace_id=workspace_id,
                    document_id=doc_id,
                    chunk_index=c.index,
                    page_start=c.page_start,
                    page_end=c.page_end,
                    text=c.text,
                    word_count=c.word_count,
                )
                for c in chunks
            ]
            # Load (or build) the index *before* the chunks exist in the DB so a
            # first-time load can't pick them up and then see them added again.
            index = self.registry.get(workspace_id)
            vectors = self.embedder.embed_documents([c.text for c in chunks])
            ids = self.db.insert_chunks(rows)
            for row, cid in zip(rows, ids, strict=True):
                row.id = cid
            index.add(rows, vectors)

            self.db.update_document(
                doc_id,
                status="ready",
                page_count=len(pages),
                chunk_count=len(chunks),
                error=None,
            )
            log.info(
                "document_indexed",
                extra={
                    "workspace": workspace_id,
                    "document": doc_id,
                    "pages": len(pages),
                    "chunks": len(chunks),
                    "seconds": round(time.perf_counter() - started, 2),
                },
            )
        except EmbeddingUnavailableError as exc:
            self.db.update_document(doc_id, status="failed", error=str(exc))
            log.error("embedding_unavailable", extra={"document": doc_id, "detail": str(exc.__cause__)[:200]})
        except AppError as exc:
            self.db.update_document(doc_id, status="failed", error=exc.message)
            log.warning("document_failed", extra={"document": doc_id, "code": exc.code})
        except Exception as exc:
            self.db.update_document(doc_id, status="failed", error="Indexing failed unexpectedly.")
            log.exception("document_crashed", extra={"document": doc_id, "detail": str(exc)[:200]})

    def delete(self, workspace_id: str, doc_id: str) -> None:
        doc = self.db.get_document(workspace_id, doc_id)
        if doc is None:
            raise NotFoundError("Document not found.", code="document_not_found")
        chunk_ids = self.db.delete_document(workspace_id, doc_id)
        self.registry.get(workspace_id).remove(chunk_ids)
        try:
            Path(doc.stored_path).unlink(missing_ok=True)
        except OSError as exc:
            log.warning("file_delete_failed", extra={"document": doc_id, "detail": str(exc)})
