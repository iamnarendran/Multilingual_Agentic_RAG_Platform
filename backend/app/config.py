"""Application settings, loaded from environment variables (and an optional .env file)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-insecure-secret-change-me-in-production-please"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App -----------------------------------------------------------------
    app_name: str = "Multilingual Agentic RAG"
    app_version: str = "2.0.0"
    environment: str = "development"  # development | production | test
    log_level: str = "INFO"
    api_prefix: str = "/api"
    cors_origins: str = "http://localhost:3000"  # comma-separated
    data_dir: Path = Path("./data")

    # --- Auth ----------------------------------------------------------------
    jwt_secret: str = DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7

    # --- Database ------------------------------------------------------------
    # SQLite by default (zero setup). Use postgresql+asyncpg://... in production.
    database_url: str | None = None

    # --- LLM (any OpenAI-compatible endpoint; OpenRouter by default) ---------
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_api_key: str = ""
    llm_model: str = "openai/gpt-oss-120b"  # answer generation
    llm_fast_model: str = "openai/gpt-oss-20b"  # routing, planning, grading, validation
    router_model: str | None = None
    planner_model: str | None = None
    grader_model: str | None = None
    generator_model: str | None = None
    validator_model: str | None = None
    llm_timeout_seconds: float = 90.0

    # --- Embeddings ----------------------------------------------------------
    embedding_provider: str = "fastembed"  # fastembed (local, free) | openai (any OpenAI-compatible API)
    embedding_model: str = "intfloat/multilingual-e5-large"
    embedding_dim: int = 1024
    embedding_batch_size: int = 16
    embedding_base_url: str | None = None  # defaults to llm_base_url
    embedding_api_key: str | None = None  # defaults to llm_api_key
    model_cache_dir: Path | None = None

    # --- Vector store (Qdrant) -----------------------------------------------
    qdrant_url: str | None = None  # empty -> embedded local mode under data_dir/qdrant
    qdrant_api_key: str | None = None
    qdrant_collection: str = "documents"

    # --- Ingestion -----------------------------------------------------------
    max_upload_mb: int = 25
    allowed_extensions: str = "pdf,docx,txt,md,csv"
    chunk_size: int = 1000  # characters
    chunk_overlap: int = 150
    ocr_enabled: bool = True
    ocr_languages: str = "eng+hin+tam+tel+kan+mal+ben+guj+pan+mar+ori+urd"
    ocr_dpi: int = 200

    # --- Retrieval & agents --------------------------------------------------
    retrieval_candidates_per_query: int = 20
    grader_candidates: int = 10
    top_k_sources: int = 6
    max_retrieval_attempts: int = 2
    history_turns: int = 6
    validation_enabled: bool = True

    # --- Derived helpers -----------------------------------------------------
    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_extension_set(self) -> set[str]:
        return {e.strip().lower().lstrip(".") for e in self.allowed_extensions.split(",") if e.strip()}

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def resolved_database_url(self) -> str:
        return self.database_url or f"sqlite+aiosqlite:///{(self.data_dir / 'app.db').as_posix()}"

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key)

    def model_for(self, agent: str) -> str:
        override = getattr(self, f"{agent}_model", None)
        if override:
            return override
        return self.llm_model if agent == "generator" else self.llm_fast_model

    @model_validator(mode="after")
    def _check_production_secret(self) -> Settings:
        if not self.jwt_secret.strip():  # "JWT_SECRET=" left blank in .env counts as unset
            self.jwt_secret = DEV_JWT_SECRET
        if self.environment == "production" and (self.jwt_secret == DEV_JWT_SECRET or len(self.jwt_secret) < 32):
            raise ValueError(
                "Set JWT_SECRET to a random value of 32+ characters in production (`openssl rand -hex 32`)."
            )
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
