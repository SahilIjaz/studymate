"""SQLite persistence for documents, chunks, conversations and messages.

SQLite is deliberate: one file, zero ops, WAL mode for concurrent readers, and
a tiny repository layer that keeps SQL out of the request handlers. Swapping
in Postgres (and pgvector for the vectors) means re-implementing this module
and nothing else.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id            TEXT PRIMARY KEY,
    workspace_id  TEXT NOT NULL,
    filename      TEXT NOT NULL,
    stored_path   TEXT NOT NULL,
    sha256        TEXT NOT NULL,
    size_bytes    INTEGER NOT NULL,
    page_count    INTEGER NOT NULL DEFAULT 0,
    chunk_count   INTEGER NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'processing',
    error         TEXT,
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_documents_workspace ON documents(workspace_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_hash ON documents(workspace_id, sha256);

CREATE TABLE IF NOT EXISTS chunks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id  TEXT NOT NULL,
    document_id   TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index   INTEGER NOT NULL,
    page_start    INTEGER NOT NULL,
    page_end      INTEGER NOT NULL,
    text          TEXT NOT NULL,
    word_count    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_workspace ON chunks(workspace_id);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id, chunk_index);

CREATE TABLE IF NOT EXISTS conversations (
    id            TEXT PRIMARY KEY,
    workspace_id  TEXT NOT NULL,
    title         TEXT NOT NULL,
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conversations_workspace ON conversations(workspace_id, updated_at);

CREATE TABLE IF NOT EXISTS messages (
    id               TEXT PRIMARY KEY,
    conversation_id  TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role             TEXT NOT NULL,
    content          TEXT NOT NULL,
    citations_json   TEXT,
    usage_json       TEXT,
    status           TEXT NOT NULL DEFAULT 'complete',
    created_at       REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, created_at);
"""


@dataclass(slots=True)
class DocumentRow:
    id: str
    workspace_id: str
    filename: str
    stored_path: str
    sha256: str
    size_bytes: int
    page_count: int
    chunk_count: int
    status: str
    error: str | None
    created_at: float
    updated_at: float


@dataclass(slots=True)
class ChunkRow:
    id: int
    workspace_id: str
    document_id: str
    chunk_index: int
    page_start: int
    page_end: int
    text: str
    word_count: int


@dataclass(slots=True)
class ConversationRow:
    id: str
    workspace_id: str
    title: str
    created_at: float
    updated_at: float


@dataclass(slots=True)
class MessageRow:
    id: str
    conversation_id: str
    role: str
    content: str
    citations: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] | None = None
    status: str = "complete"
    created_at: float = 0.0


def _row_to(cls: type, row: sqlite3.Row) -> Any:
    return cls(**{k: row[k] for k in row.keys()})  # noqa: SIM118 - sqlite3.Row iterates values


class Database:
    """Thread-safe SQLite wrapper. One connection per thread, WAL journal."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._local = threading.local()
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, check_same_thread=False, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._connect()
            self._local.conn = conn
        yield conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except Exception:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # ------------------------------------------------------------------ documents
    def insert_document(self, doc: DocumentRow) -> None:
        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO documents
                   (id, workspace_id, filename, stored_path, sha256, size_bytes, page_count,
                    chunk_count, status, error, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    doc.id,
                    doc.workspace_id,
                    doc.filename,
                    doc.stored_path,
                    doc.sha256,
                    doc.size_bytes,
                    doc.page_count,
                    doc.chunk_count,
                    doc.status,
                    doc.error,
                    doc.created_at,
                    doc.updated_at,
                ),
            )

    def update_document(self, doc_id: str, **fields: Any) -> None:
        fields["updated_at"] = time.time()
        assignments = ", ".join(f"{k} = ?" for k in fields)
        with self.transaction() as conn:
            conn.execute(
                f"UPDATE documents SET {assignments} WHERE id = ?",
                (*fields.values(), doc_id),
            )

    def get_document(self, workspace_id: str, doc_id: str) -> DocumentRow | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE id = ? AND workspace_id = ?",
                (doc_id, workspace_id),
            ).fetchone()
        return _row_to(DocumentRow, row) if row else None

    def find_document_by_hash(self, workspace_id: str, sha256: str) -> DocumentRow | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE workspace_id = ? AND sha256 = ?",
                (workspace_id, sha256),
            ).fetchone()
        return _row_to(DocumentRow, row) if row else None

    def list_documents(self, workspace_id: str) -> list[DocumentRow]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM documents WHERE workspace_id = ? ORDER BY created_at DESC",
                (workspace_id,),
            ).fetchall()
        return [_row_to(DocumentRow, r) for r in rows]

    def count_documents(self, workspace_id: str) -> int:
        with self.connection() as conn:
            return int(
                conn.execute(
                    "SELECT COUNT(*) FROM documents WHERE workspace_id = ?",
                    (workspace_id,),
                ).fetchone()[0]
            )

    def delete_document(self, workspace_id: str, doc_id: str) -> list[int]:
        """Delete a document and return the ids of the chunks that went with it."""
        with self.transaction() as conn:
            chunk_ids = [
                int(r[0])
                for r in conn.execute(
                    "SELECT id FROM chunks WHERE document_id = ? AND workspace_id = ?",
                    (doc_id, workspace_id),
                ).fetchall()
            ]
            conn.execute(
                "DELETE FROM documents WHERE id = ? AND workspace_id = ?",
                (doc_id, workspace_id),
            )
        return chunk_ids

    # --------------------------------------------------------------------- chunks
    def insert_chunks(self, chunks: list[ChunkRow]) -> list[int]:
        ids: list[int] = []
        with self.transaction() as conn:
            for c in chunks:
                cur = conn.execute(
                    """INSERT INTO chunks
                       (workspace_id, document_id, chunk_index, page_start, page_end, text, word_count)
                       VALUES (?,?,?,?,?,?,?)""",
                    (
                        c.workspace_id,
                        c.document_id,
                        c.chunk_index,
                        c.page_start,
                        c.page_end,
                        c.text,
                        c.word_count,
                    ),
                )
                ids.append(int(cur.lastrowid))
        return ids

    def list_chunks(self, workspace_id: str) -> list[ChunkRow]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM chunks WHERE workspace_id = ? ORDER BY id",
                (workspace_id,),
            ).fetchall()
        return [_row_to(ChunkRow, r) for r in rows]

    def get_chunks(self, workspace_id: str, ids: list[int]) -> dict[int, ChunkRow]:
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        with self.connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM chunks WHERE workspace_id = ? AND id IN ({placeholders})",
                (workspace_id, *ids),
            ).fetchall()
        return {int(r["id"]): _row_to(ChunkRow, r) for r in rows}

    def first_chunks(self, workspace_id: str, document_id: str, limit: int) -> list[ChunkRow]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM chunks WHERE workspace_id = ? AND document_id = ? ORDER BY chunk_index LIMIT ?",
                (workspace_id, document_id, limit),
            ).fetchall()
        return [_row_to(ChunkRow, r) for r in rows]

    # -------------------------------------------------------------- conversations
    def insert_conversation(self, convo: ConversationRow) -> None:
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO conversations (id, workspace_id, title, created_at, updated_at) VALUES (?,?,?,?,?)",
                (
                    convo.id,
                    convo.workspace_id,
                    convo.title,
                    convo.created_at,
                    convo.updated_at,
                ),
            )

    def get_conversation(self, workspace_id: str, convo_id: str) -> ConversationRow | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM conversations WHERE id = ? AND workspace_id = ?",
                (convo_id, workspace_id),
            ).fetchone()
        return _row_to(ConversationRow, row) if row else None

    def list_conversations(self, workspace_id: str) -> list[ConversationRow]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM conversations WHERE workspace_id = ? ORDER BY updated_at DESC",
                (workspace_id,),
            ).fetchall()
        return [_row_to(ConversationRow, r) for r in rows]

    def touch_conversation(self, convo_id: str, title: str | None = None) -> None:
        with self.transaction() as conn:
            if title is not None:
                conn.execute(
                    "UPDATE conversations SET updated_at = ?, title = ? WHERE id = ?",
                    (time.time(), title, convo_id),
                )
            else:
                conn.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?",
                    (time.time(), convo_id),
                )

    def delete_conversation(self, workspace_id: str, convo_id: str) -> bool:
        with self.transaction() as conn:
            cur = conn.execute(
                "DELETE FROM conversations WHERE id = ? AND workspace_id = ?",
                (convo_id, workspace_id),
            )
        return cur.rowcount > 0

    # ------------------------------------------------------------------- messages
    def insert_message(self, msg: MessageRow) -> None:
        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO messages
                   (id, conversation_id, role, content, citations_json, usage_json, status, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    msg.id,
                    msg.conversation_id,
                    msg.role,
                    msg.content,
                    json.dumps(msg.citations) if msg.citations else None,
                    json.dumps(msg.usage) if msg.usage else None,
                    msg.status,
                    msg.created_at,
                ),
            )

    def list_messages(self, conversation_id: str, limit: int | None = None) -> list[MessageRow]:
        sql = "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at"
        params: tuple[Any, ...] = (conversation_id,)
        if limit:
            sql = f"SELECT * FROM ({sql} DESC LIMIT ?) ORDER BY created_at"
            params = (conversation_id, limit)
        with self.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            MessageRow(
                id=r["id"],
                conversation_id=r["conversation_id"],
                role=r["role"],
                content=r["content"],
                citations=json.loads(r["citations_json"]) if r["citations_json"] else [],
                usage=json.loads(r["usage_json"]) if r["usage_json"] else None,
                status=r["status"],
                created_at=r["created_at"],
            )
            for r in rows
        ]
