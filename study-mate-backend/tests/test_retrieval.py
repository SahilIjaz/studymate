from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.config import Settings
from app.services.embeddings import HashedEmbedder
from app.services.index import IndexRegistry, WorkspaceIndex, tokenize
from app.services.retrieval import is_overview_question, retrieve
from app.storage.db import ChunkRow, Database, DocumentRow

WS = "11111111-2222-3333-4444-555555555555"


def _seed(db: Database, texts: dict[str, list[str]]) -> dict[str, str]:
    """Insert one document per key with the given chunk texts. Returns doc ids."""
    ids: dict[str, str] = {}
    for name, chunks in texts.items():
        doc_id = f"doc_{name}"
        ids[name] = doc_id
        now = time.time()
        db.insert_document(
            DocumentRow(
                doc_id,
                WS,
                f"{name}.pdf",
                f"/tmp/{doc_id}.pdf",
                f"sha-{name}",
                10,
                1,
                len(chunks),
                "ready",
                None,
                now,
                now,
            )
        )
        rows = [ChunkRow(0, WS, doc_id, i, 1, 1, text, len(text.split())) for i, text in enumerate(chunks)]
        for row, cid in zip(rows, db.insert_chunks(rows), strict=True):
            row.id = cid
    return ids


@pytest.fixture
def env(tmp_path: Path) -> tuple[Database, IndexRegistry, Settings]:
    settings = Settings(
        data_dir=tmp_path, embedding_provider="hashed", min_dense_similarity=0.05, _env_file=None
    )
    db = Database(tmp_path / "db.sqlite")
    registry = IndexRegistry(tmp_path / "ws", HashedEmbedder(), db)
    return db, registry, settings


def test_tokenize_drops_stopwords_and_punctuation() -> None:
    assert tokenize("What is the Calvin cycle?") == ["calvin", "cycle"]


def test_hybrid_retrieval_finds_relevant_chunk_and_scopes(env) -> None:
    db, registry, settings = env
    ids = _seed(
        db,
        {
            "bio": [
                "Photosynthesis converts light energy into chemical energy inside chloroplasts.",
                "Mitosis divides a nucleus into two identical nuclei through four phases.",
            ],
            "hist": ["The Treaty of Westphalia in 1648 ended the Thirty Years War in Europe."],
        },
    )
    index = registry.get(WS)  # first load builds vectors from the DB
    embedder = registry.embedder
    assert index.size == 3

    hits = retrieve(
        question="Where does photosynthesis happen?", index=index, embedder=embedder, db=db, settings=settings
    )
    assert hits and "chloroplasts" in hits[0].chunk.text
    assert hits[0].score == 1.0

    scoped = retrieve(
        question="photosynthesis",
        index=index,
        embedder=embedder,
        db=db,
        settings=settings,
        document_ids={ids["hist"]},
    )
    assert all(h.chunk.document_id == ids["hist"] for h in scoped)

    nothing = retrieve(
        question="quantum chromodynamics gluons", index=index, embedder=embedder, db=db, settings=settings
    )
    assert nothing == []


def test_index_persists_and_reloads_with_matching_count(tmp_path: Path, env) -> None:
    db, registry, _ = env
    _seed(db, {"a": ["alpha beta gamma", "delta epsilon"]})
    index = registry.get(WS)
    chunks = db.list_chunks(WS)
    assert index.size == 2
    # Re-adding the same chunks is a no-op.
    index.add(chunks, registry.embedder.embed_documents([c.text for c in chunks]))
    assert index.size == 2

    reloaded = WorkspaceIndex(WS, tmp_path / "ws" / WS, registry.embedder, db)
    assert reloaded.size == 2
    assert reloaded.search_sparse("epsilon", 5)[0].chunk_id == chunks[1].id


def test_remove_drops_vectors_and_keywords(env) -> None:
    db, registry, _ = env
    ids = _seed(db, {"a": ["alpha beta gamma"], "b": ["delta epsilon zeta"]})
    index = registry.get(WS)
    assert index.size == 2

    removed = db.delete_document(WS, ids["a"])
    index.remove(removed)
    assert index.size == 1
    assert index.search_sparse("alpha", 5) == []
    assert index.search_sparse("zeta", 5)


def test_provider_change_triggers_reindex(tmp_path: Path, env) -> None:
    db, registry, _ = env
    _seed(db, {"a": ["alpha beta gamma"]})
    registry.get(WS)
    chunks = db.list_chunks(WS)

    class OtherEmbedder(HashedEmbedder):
        name = "hashed-other"
        dimension = 128

    rebuilt = WorkspaceIndex(WS, tmp_path / "ws" / WS, OtherEmbedder(), db)
    assert rebuilt.size == 1
    assert rebuilt.search_dense(OtherEmbedder().embed_query("alpha"), 1)[0].chunk_id == chunks[0].id


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Summarize this document", True),
        ("What are the main points?", True),
        ("Give me a TL;DR", True),
        ("What is the Calvin cycle?", False),
    ],
)
def test_overview_detection(question: str, expected: bool) -> None:
    assert is_overview_question(question) is expected
