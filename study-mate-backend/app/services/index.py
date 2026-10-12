"""Per-workspace search index: FAISS for dense vectors, BM25 for keywords.

Why both: dense embeddings catch paraphrases ("car" ~ "automobile"); BM25
catches exact terms, identifiers and rare words that small embedding models
blur. The two result lists are fused in `retrieval.py`.

Persistence: the FAISS index is written to disk after every mutation and the
BM25 index is rebuilt from SQLite on load (cheap at study-notes scale). The
workspace's metadata file records which embedder built the index so a
provider change can be detected and the vectors rebuilt.
"""

from __future__ import annotations

import json
import re
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

import faiss
import numpy as np
from rank_bm25 import BM25Plus

from app.logging_config import get_logger
from app.services.embeddings import Embedder
from app.storage.db import ChunkRow, Database

log = get_logger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "were",
        "will",
        "with",
        "what",
        "which",
        "who",
        "whom",
        "whose",
        "when",
        "where",
        "why",
        "how",
        "does",
        "do",
        "did",
        "can",
        "could",
        "should",
        "would",
        "may",
        "might",
        "shall",
        "i",
        "you",
        "he",
        "she",
        "we",
        "they",
        "them",
        "their",
        "there",
        "here",
        "than",
        "then",
        "also",
        "into",
        "onto",
        "over",
        "under",
        "about",
    ]
)


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS]


@dataclass(slots=True)
class DenseHit:
    chunk_id: int
    score: float  # cosine similarity


@dataclass(slots=True)
class SparseHit:
    chunk_id: int
    score: float  # BM25 score


class WorkspaceIndex:
    def __init__(self, workspace_id: str, directory: Path, embedder: Embedder, db: Database) -> None:
        self.workspace_id = workspace_id
        self.directory = directory
        self.embedder = embedder
        self.db = db
        self.lock = threading.RLock()
        self._faiss: faiss.IndexIDMap2 | None = None
        self._bm25: BM25Plus | None = None
        self._bm25_ids: list[int] = []
        self._chunk_doc: dict[int, str] = {}
        self.directory.mkdir(parents=True, exist_ok=True)
        self._load()

    # ------------------------------------------------------------------ paths
    @property
    def _index_path(self) -> Path:
        return self.directory / "index.faiss"

    @property
    def _meta_path(self) -> Path:
        return self.directory / "index.json"

    # ------------------------------------------------------------------- load
    def _empty_index(self) -> faiss.IndexIDMap2:
        return faiss.IndexIDMap2(faiss.IndexFlatIP(self.embedder.dimension))

    def _load(self) -> None:
        with self.lock:
            chunks = self.db.list_chunks(self.workspace_id)
            self._chunk_doc = {c.id: c.document_id for c in chunks}
            meta = {}
            if self._meta_path.exists():
                meta = json.loads(self._meta_path.read_text())
            compatible = (
                meta.get("embedder") == self.embedder.name
                and meta.get("dimension") == self.embedder.dimension
                and self._index_path.exists()
            )
            if compatible:
                self._faiss = faiss.read_index(str(self._index_path))
                if self._faiss.ntotal != len(chunks):
                    log.warning("index_out_of_sync", extra={"workspace": self.workspace_id})
                    compatible = False
            if not compatible:
                self._rebuild_dense(chunks)
            self._rebuild_sparse(chunks)

    def _rebuild_dense(self, chunks: list[ChunkRow]) -> None:
        self._faiss = self._empty_index()
        if chunks:
            log.info(
                "reindexing_workspace",
                extra={"workspace": self.workspace_id, "chunks": len(chunks)},
            )
            vectors = self.embedder.embed_documents([c.text for c in chunks])
            self._faiss.add_with_ids(
                np.ascontiguousarray(vectors, dtype="float32"),
                np.asarray([c.id for c in chunks], dtype="int64"),
            )
        self._persist()

    def _rebuild_sparse(self, chunks: list[ChunkRow]) -> None:
        self._bm25_ids = [c.id for c in chunks]
        corpus = [tokenize(c.text) for c in chunks]
        # BM25+ keeps idf positive even when a term appears in every chunk, so
        # a one-page PDF (a corpus of one or two chunks) is still searchable.
        self._bm25 = BM25Plus(corpus) if corpus else None

    def _persist(self) -> None:
        assert self._faiss is not None
        tmp = self._index_path.with_suffix(".tmp")
        faiss.write_index(self._faiss, str(tmp))
        tmp.replace(self._index_path)
        self._meta_path.write_text(
            json.dumps(
                {
                    "embedder": self.embedder.name,
                    "dimension": self.embedder.dimension,
                    "count": self._faiss.ntotal,
                }
            )
        )

    # --------------------------------------------------------------- mutation
    def add(self, chunks: list[ChunkRow], vectors: np.ndarray) -> None:
        """Add chunk vectors. Ids already present are skipped, so a workspace
        whose index was rebuilt from the database on load never double-counts."""
        with self.lock:
            assert self._faiss is not None
            fresh = [i for i, c in enumerate(chunks) if c.id not in self._chunk_doc]
            chunks = [chunks[i] for i in fresh]
            vectors = vectors[fresh] if len(fresh) else vectors[:0]
            if len(chunks):
                self._faiss.add_with_ids(
                    np.ascontiguousarray(vectors, dtype="float32"),
                    np.asarray([c.id for c in chunks], dtype="int64"),
                )
                for c in chunks:
                    self._chunk_doc[c.id] = c.document_id
            self._persist()
            self._rebuild_sparse(self.db.list_chunks(self.workspace_id))

    def remove(self, chunk_ids: list[int]) -> None:
        with self.lock:
            assert self._faiss is not None
            if chunk_ids:
                selector = faiss.IDSelectorBatch(np.asarray(chunk_ids, dtype="int64"))
                self._faiss.remove_ids(selector)
                for cid in chunk_ids:
                    self._chunk_doc.pop(cid, None)
            self._persist()
            self._rebuild_sparse(self.db.list_chunks(self.workspace_id))

    # ------------------------------------------------------------------ query
    @property
    def size(self) -> int:
        return self._faiss.ntotal if self._faiss is not None else 0

    def document_of(self, chunk_id: int) -> str | None:
        return self._chunk_doc.get(chunk_id)

    def search_dense(self, query_vector: np.ndarray, k: int) -> list[DenseHit]:
        with self.lock:
            if self._faiss is None or self._faiss.ntotal == 0:
                return []
            k = min(k, self._faiss.ntotal)
            scores, ids = self._faiss.search(np.ascontiguousarray(query_vector, dtype="float32")[None, :], k)
        return [DenseHit(int(i), float(s)) for s, i in zip(scores[0], ids[0], strict=True) if i != -1]

    def search_sparse(self, query: str, k: int) -> list[SparseHit]:
        with self.lock:
            if self._bm25 is None:
                return []
            tokens = tokenize(query)
            if not tokens:
                return []
            scores = self._bm25.get_scores(tokens)
            # BM25+ adds idf*delta for every query term regardless of a match;
            # strip that constant so chunks with no matching term score 0.
            baseline = sum((self._bm25.idf.get(t) or 0.0) * self._bm25.delta for t in tokens)
            scores = scores - baseline
            order = np.argsort(scores)[::-1][:k]
            return [SparseHit(self._bm25_ids[int(i)], float(scores[i])) for i in order if scores[i] > 0]


class IndexRegistry:
    """Bounded cache of loaded workspace indexes."""

    def __init__(self, root: Path, embedder: Embedder, db: Database, max_loaded: int = 64) -> None:
        self.root = root
        self.embedder = embedder
        self.db = db
        self.max_loaded = max_loaded
        self._cache: OrderedDict[str, WorkspaceIndex] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, workspace_id: str) -> WorkspaceIndex:
        with self._lock:
            index = self._cache.get(workspace_id)
            if index is not None:
                self._cache.move_to_end(workspace_id)
                return index
        # Build outside the registry lock: loading may embed thousands of chunks.
        index = WorkspaceIndex(workspace_id, self.root / workspace_id, self.embedder, self.db)
        with self._lock:
            existing = self._cache.get(workspace_id)
            if existing is not None:
                return existing
            self._cache[workspace_id] = index
            while len(self._cache) > self.max_loaded:
                self._cache.popitem(last=False)
        return index

    def evict(self, workspace_id: str) -> None:
        with self._lock:
            self._cache.pop(workspace_id, None)
