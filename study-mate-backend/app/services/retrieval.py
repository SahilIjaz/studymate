"""Hybrid retrieval: dense + BM25 candidates fused with reciprocal rank fusion.

RRF needs no score calibration between the two systems, which is exactly the
problem with mixing cosine similarities and BM25 scores directly. After the
fusion, weak tails are cut relative to the best hit so an off-topic question
yields *no* sources instead of five irrelevant ones.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import Settings
from app.services.embeddings import Embedder
from app.services.index import WorkspaceIndex
from app.storage.db import ChunkRow, Database

_RRF_K = 60.0


@dataclass(slots=True)
class RetrievedChunk:
    chunk: ChunkRow
    score: float  # 0..1, relative to the best hit
    dense_similarity: float | None
    sparse_score: float | None
    filename: str = "document"


_OVERVIEW_RE = re.compile(
    r"\b(summar(y|ise|ize)|overview|outline|tl;?dr|main (points|ideas|topics|arguments)|key (points|ideas|takeaways)|"
    r"what (is|are) (this|the|these) (document|pdf|file|paper|notes?|chapter)s? about|what does (this|the) (document|pdf|file|paper) (cover|say|discuss))\b",
    re.IGNORECASE,
)


def is_overview_question(question: str) -> bool:
    """Whole-document questions can't be answered by similarity search alone."""
    return bool(_OVERVIEW_RE.search(question))


def overview_chunks(
    db: Database, workspace_id: str, document_ids: list[str], top_k: int
) -> list[RetrievedChunk]:
    """Leading chunks of each document, interleaved, so a summary sees every file."""
    per_doc = max(1, top_k // max(1, len(document_ids)))
    lanes = [db.first_chunks(workspace_id, doc_id, per_doc + 1) for doc_id in document_ids]
    out: list[RetrievedChunk] = []
    position = 0
    while len(out) < top_k and any(position < len(lane) for lane in lanes):
        for lane in lanes:
            if position < len(lane) and len(out) < top_k:
                out.append(
                    RetrievedChunk(
                        chunk=lane[position],
                        score=1.0,
                        dense_similarity=None,
                        sparse_score=None,
                    )
                )
        position += 1
    return out


def retrieve(
    *,
    question: str,
    index: WorkspaceIndex,
    embedder: Embedder,
    db: Database,
    settings: Settings,
    document_ids: set[str] | None = None,
) -> list[RetrievedChunk]:
    if index.size == 0:
        return []

    pool = settings.candidate_pool
    query_vector = embedder.embed_query(question)
    dense = index.search_dense(query_vector, pool)
    sparse = index.search_sparse(question, pool)

    # Scope to the requested documents, if any.
    if document_ids:
        dense = [h for h in dense if index.document_of(h.chunk_id) in document_ids]
        sparse = [h for h in sparse if index.document_of(h.chunk_id) in document_ids]

    # Filter dense noise before ranking so a hit must earn its place.
    dense = [h for h in dense if h.score >= settings.min_dense_similarity]

    fused: dict[int, float] = {}
    dense_by_id = {h.chunk_id: h.score for h in dense}
    sparse_by_id = {h.chunk_id: h.score for h in sparse}
    for rank, hit in enumerate(dense):
        fused[hit.chunk_id] = fused.get(hit.chunk_id, 0.0) + 1.0 / (_RRF_K + rank + 1)
    for rank, hit in enumerate(sparse):
        fused[hit.chunk_id] = fused.get(hit.chunk_id, 0.0) + 1.0 / (_RRF_K + rank + 1)

    if not fused:
        return []

    best = max(fused.values())
    ranked = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)
    kept = [(cid, s) for cid, s in ranked if s / best >= settings.min_relative_score][: settings.top_k]

    rows = db.get_chunks(index.workspace_id, [cid for cid, _ in kept])
    results: list[RetrievedChunk] = []
    for cid, score in kept:
        row = rows.get(cid)
        if row is None:
            continue
        results.append(
            RetrievedChunk(
                chunk=row,
                score=round(score / best, 4),
                dense_similarity=round(dense_by_id[cid], 4) if cid in dense_by_id else None,
                sparse_score=round(sparse_by_id[cid], 4) if cid in sparse_by_id else None,
            )
        )
    return results
