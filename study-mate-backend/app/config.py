"""Application settings.

Every tunable lives here and is read from the environment (or a local `.env`)
so the same image runs unchanged in local, CI and production.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

EmbeddingProvider = Literal["auto", "gemini", "fastembed", "voyage", "hashed"]
LLMProvider = Literal["auto", "gemini", "claude", "mock"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- service -----------------------------------------------------------
    app_name: str = "StudyMate API"
    app_version: str = "2.0.0"
    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    data_dir: Path = Field(default=Path("data"))
    # NoDecode: read as a plain comma-separated string, split in the validator below.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    # Optional shared secret. When set, every request must carry it in
    # `X-API-Key`. Left empty for the public demo; real deployments put an
    # identity provider in front of this instead.
    app_api_key: str | None = None

    # --- LLM ----------------------------------------------------------------
    # auto = gemini if GEMINI_API_KEY is set, else claude if ANTHROPIC_API_KEY is set.
    llm_provider: LLMProvider = "auto"

    # Gemini (free tier friendly)
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash"
    # Thinking depth for Gemini 3.x models ("low" keeps first-token latency ~2 s). Empty = model default.
    gemini_thinking_level: str | None = "low"
    # Used when the primary model is overloaded (503) or rate-limited before any text arrived.
    gemini_fallback_model: str = "gemini-flash-lite-latest"
    gemini_fast_model: str = "gemini-flash-lite-latest"

    # Claude
    anthropic_api_key: str | None = None
    claude_model: str = "claude-opus-5-5"
    # Small, fast model for side tasks (query rewriting, question suggestions).
    claude_fast_model: str = "claude-haiku-5-5"
    claude_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    claude_max_tokens: int = 8192
    # Server-side refusal fallbacks (beta). Re-runs a declined request on a
    # fallback model inside the same call. Disable if your org lacks the beta.
    claude_server_fallbacks: bool = True
    claude_timeout_seconds: float = 120.0
    # Dev only: stream canned answers instead of calling a model (no key needed).
    llm_mock: bool = False
    history_turns: int = 6
    query_rewrite: bool = True

    # --- embeddings & retrieval -------------------------------------------
    embedding_provider: EmbeddingProvider = "auto"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    # Where fastembed keeps downloaded models. Defaults under DATA_DIR so it
    # survives reboots (the library default is the system temp directory).
    embedding_cache_dir: Path | None = None
    # Gemini embeddings (free tier). Dimension is truncated server-side (MRL).
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_embedding_dim: int = 768
    voyage_api_key: str | None = None
    voyage_model: str = "voyage-3.5-lite"
    chunk_size_words: int = 300
    chunk_overlap_words: int = 60
    top_k: int = 6
    candidate_pool: int = 24
    # Chunks whose fused relevance falls below this fraction of the best hit
    # are dropped so weak matches never reach the prompt.
    min_relative_score: float = 0.35
    # Dense cosine similarity below which a hit is treated as noise.
    min_dense_similarity: float = 0.25

    # --- limits -------------------------------------------------------------
    max_upload_mb: int = 20
    max_pages: int = 300
    max_docs_per_workspace: int = 20
    max_question_chars: int = 2000
    rate_limit_ask_per_minute: int = 12
    rate_limit_upload_per_minute: int = 6

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def resolved_llm_provider(self) -> LLMProvider:
        if self.llm_provider != "auto":
            return self.llm_provider
        if self.llm_mock:
            return "mock"
        if self.gemini_api_key:
            return "gemini"
        return "claude"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def workspaces_dir(self) -> Path:
        return self.data_dir / "workspaces"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "studymate.db"

    @property
    def model_cache_dir(self) -> Path:
        return self.embedding_cache_dir or (self.data_dir / "models")


@lru_cache
def get_settings() -> Settings:
    return Settings()
