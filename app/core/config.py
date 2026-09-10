from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    api_key: str = ""

    database_url: str = "postgresql+psycopg://tracerag:tracerag@localhost:5432/tracerag"
    redis_url: str = "redis://localhost:6379/0"
    storage_dir: Path = Path("storage")
    max_upload_mb: int = 20
    ingestion_mode: str = "inline"

    embedding_backend: str = "fastembed"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    rerank_backend: str = "fastembed"
    rerank_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"

    llm_backend: str = "mock"
    llm_base_url: str = "https://api.example.com/v1"
    llm_api_key: str = ""
    llm_model: str = "your-chat-model"
    llm_timeout_seconds: float = 60.0
    llm_temperature: float = 0.1

    chunk_target_chars: int = 1400
    chunk_overlap_chars: int = 180
    dense_k: int = 20
    sparse_k: int = 20
    # How many RRF candidates the cross-encoder sees. Measured on the 30-case
    # benchmark: 12 candidates scored recall@5 0.9722 / MRR 0.9833 at 417 ms p50,
    # while 6 scored recall@5 0.9833 / MRR 0.9833 at ~355 ms -- a larger pool let
    # the reranker promote a distractor above the gold document. See
    # DEBUG_REPORT.md "Optimizations".
    rerank_candidates: int = 6
    default_top_k: int = 6
    rrf_k: int = 60
    retrieval_cache_ttl_seconds: int = 300
    max_agent_steps: int = 5
    chat_history_messages: int = 6

    otel_service_name: str = "tracerag"
    otel_exporter_otlp_endpoint: str = ""

    @field_validator("ingestion_mode")
    @classmethod
    def validate_ingestion_mode(cls, value: str) -> str:
        value = value.lower()
        if value not in {"inline", "celery"}:
            raise ValueError("INGESTION_MODE must be inline or celery")
        return value

    @field_validator("embedding_backend")
    @classmethod
    def validate_embedding_backend(cls, value: str) -> str:
        value = value.lower()
        if value not in {"fastembed", "hash"}:
            raise ValueError("EMBEDDING_BACKEND must be fastembed or hash")
        return value

    @field_validator("rerank_backend")
    @classmethod
    def validate_rerank_backend(cls, value: str) -> str:
        value = value.lower()
        if value not in {"fastembed", "none"}:
            raise ValueError("RERANK_BACKEND must be fastembed or none")
        return value

    @field_validator("llm_backend")
    @classmethod
    def validate_llm_backend(cls, value: str) -> str:
        value = value.lower()
        if value not in {"mock", "openai_compatible"}:
            raise ValueError("LLM_BACKEND must be mock or openai_compatible")
        return value

    @property
    def upload_dir(self) -> Path:
        return self.storage_dir / "uploads"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    return settings


settings = get_settings()
