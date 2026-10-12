"""Embedding providers behind one small interface.

Three implementations, chosen by `EMBEDDING_PROVIDER`:

- `gemini`    - Gemini embedding API (free tier, no download; default when a
                GEMINI_API_KEY is present).
- `voyage`    - Voyage AI hosted embeddings (best quality, needs an API key).
- `fastembed` - local ONNX sentence embeddings (bge-small by default). No
                torch, ~130 MB model cached on first use, fits a small dyno.
- `hashed`    - the original hashed bag-of-words. Kept as the dependency-free
                fallback used in tests; it is *not* a semantic model.

`auto` picks the best one available. Each workspace index records which
provider built it, so a provider change triggers a transparent re-index.
"""

from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path
from typing import ClassVar, Protocol

import httpx
import numpy as np

from app.config import Settings
from app.logging_config import get_logger

log = get_logger(__name__)


class EmbeddingUnavailableError(RuntimeError):
    """The embedding backend could not be initialised (model download, API)."""


class Embedder(Protocol):
    name: str
    dimension: int

    def embed_documents(self, texts: list[str]) -> np.ndarray: ...
    def embed_query(self, text: str) -> np.ndarray: ...


def _normalize(matrix: np.ndarray) -> np.ndarray:
    matrix = np.asarray(matrix, dtype="float32")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


class HashedEmbedder:
    """Deterministic hashed bag-of-words. Fast, tiny, lexical only."""

    name = "hashed-bow-384"
    dimension = 384

    def _vector(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dimension, dtype="float32")
        for token in text.lower().split():
            token = token.strip(".,;:!?()[]{}\"'")
            if not token:
                continue
            bucket = int(hashlib.md5(token.encode(), usedforsecurity=False).hexdigest(), 16) % self.dimension
            vec[bucket] += 1.0
        return vec

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return _normalize(
            np.stack([self._vector(t) for t in texts]) if texts else np.zeros((0, self.dimension))
        )

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed_documents([text])[0]


class FastEmbedEmbedder:
    """Local ONNX model via fastembed. Loaded lazily and only once."""

    def __init__(self, model_name: str, cache_dir: Path | None = None) -> None:
        self.name = f"fastembed:{model_name}"
        self._model_name = model_name
        self._cache_dir = cache_dir
        self._model = None
        self._lock = threading.Lock()
        self.dimension = self._lookup_dimension(model_name)

    @staticmethod
    def _lookup_dimension(model_name: str) -> int:
        from fastembed import TextEmbedding

        for desc in TextEmbedding.list_supported_models():
            if desc["model"] == model_name:
                return int(desc["dim"])
        raise ValueError(f"Unknown fastembed model: {model_name}")

    def _get(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from fastembed import TextEmbedding

                    log.info(
                        "loading_embedding_model",
                        extra={"model": self._model_name, "cache": str(self._cache_dir)},
                    )
                    if self._cache_dir:
                        self._cache_dir.mkdir(parents=True, exist_ok=True)
                    try:
                        self._model = TextEmbedding(
                            model_name=self._model_name,
                            cache_dir=str(self._cache_dir) if self._cache_dir else None,
                        )
                    except Exception as exc:
                        raise EmbeddingUnavailableError(
                            f"The embedding model {self._model_name} couldn't be loaded (download failed?). "
                            "Check the server's network access and try again."
                        ) from exc
        return self._model

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimension), dtype="float32")
        vectors = list(self._get().embed(texts, batch_size=32))
        return _normalize(np.stack(vectors))

    def embed_query(self, text: str) -> np.ndarray:
        vector = next(iter(self._get().query_embed(text)))
        return _normalize(np.asarray(vector)[None, :])[0]


class VoyageEmbedder:
    """Voyage AI REST API, called with httpx so no extra SDK is needed."""

    _DIMENSIONS: ClassVar[dict[str, int]] = {
        "voyage-3.5": 1024,
        "voyage-3.5-lite": 1024,
        "voyage-3-large": 1024,
        "voyage-3": 1024,
    }

    def __init__(self, api_key: str, model: str) -> None:
        self.name = f"voyage:{model}"
        self._model = model
        self.dimension = self._DIMENSIONS.get(model, 1024)
        self._client = httpx.Client(
            base_url="https://api.voyageai.com/v1",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60.0,
        )

    def _call(self, texts: list[str], input_type: str) -> np.ndarray:
        out: list[list[float]] = []
        for start in range(0, len(texts), 64):
            batch = texts[start : start + 64]
            resp = self._client.post(
                "/embeddings",
                json={"input": batch, "model": self._model, "input_type": input_type},
            )
            resp.raise_for_status()
            data = sorted(resp.json()["data"], key=lambda d: d["index"])
            out.extend(d["embedding"] for d in data)
        return _normalize(np.asarray(out, dtype="float32"))

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimension), dtype="float32")
        return self._call(texts, "document")

    def embed_query(self, text: str) -> np.ndarray:
        return self._call([text], "query")[0]


class GeminiEmbedder:
    """Gemini embedding API. No model download, tiny memory footprint, free tier."""

    _BATCH = 64

    def __init__(self, api_key: str, model: str, dimension: int) -> None:
        from google import genai
        from google.genai import types

        self.name = f"gemini:{model}:{dimension}"
        self.dimension = dimension
        self._model = model
        self._types = types
        self._client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=60_000))

    def _call(self, texts: list[str], task: str) -> np.ndarray:
        from google.genai import errors

        out: list[list[float]] = []
        for start in range(0, len(texts), self._BATCH):
            batch = texts[start : start + self._BATCH]
            config = self._types.EmbedContentConfig(task_type=task, output_dimensionality=self.dimension)
            for attempt in range(4):
                try:
                    response = self._client.models.embed_content(
                        model=self._model, contents=batch, config=config
                    )
                    break
                except errors.APIError as exc:
                    if exc.code not in (429, 503) or attempt == 3:
                        raise EmbeddingUnavailableError(
                            f"Gemini embeddings failed ({exc.code}): {exc.message}"
                        ) from exc
                    log.warning("gemini_embed_retry", extra={"status": exc.code, "attempt": attempt + 1})
                    time.sleep(2.0 * (attempt + 1))
            out.extend(e.values for e in response.embeddings)
        return _normalize(np.asarray(out, dtype="float32"))

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimension), dtype="float32")
        return self._call(texts, "RETRIEVAL_DOCUMENT")

    def embed_query(self, text: str) -> np.ndarray:
        return self._call([text], "RETRIEVAL_QUERY")[0]


def build_embedder(settings: Settings) -> Embedder:
    provider = settings.embedding_provider
    if provider == "auto":
        if settings.voyage_api_key:
            provider = "voyage"
        elif settings.gemini_api_key:
            provider = "gemini"
        else:
            try:
                import fastembed  # noqa: F401

                provider = "fastembed"
            except ImportError:
                provider = "hashed"

    if provider == "gemini":
        if not settings.gemini_api_key:
            raise RuntimeError("EMBEDDING_PROVIDER=gemini requires GEMINI_API_KEY")
        return GeminiEmbedder(
            settings.gemini_api_key, settings.gemini_embedding_model, settings.gemini_embedding_dim
        )

    if provider == "voyage":
        if not settings.voyage_api_key:
            raise RuntimeError("EMBEDDING_PROVIDER=voyage requires VOYAGE_API_KEY")
        return VoyageEmbedder(settings.voyage_api_key, settings.voyage_model)
    if provider == "fastembed":
        return FastEmbedEmbedder(settings.embedding_model, cache_dir=settings.model_cache_dir)
    return HashedEmbedder()
