"""Application configuration using Pydantic V2 BaseSettings.

All settings are loaded from environment variables via .env file.
"""

from enum import StrEnum
from pathlib import Path

from pydantic import (
    Field,
    HttpUrl,
    PostgresDsn,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class LogFormat(StrEnum):
    """Supported log output formats."""

    JSON = "json"
    TEXT = "text"


class Environment(StrEnum):
    """Deployment environment."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Centralized application settings.

    Loaded from environment variables and .env file.
    All values are validated at startup.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        frozen=True,
    )

    # ── General ────────────────────────────────
    PROJECT_NAME: str = "Enterprise RAG Platform"
    ENVIRONMENT: Environment = Environment.DEVELOPMENT
    DEBUG: bool = True
    SECRET_KEY: str = Field(
        default="change-me",
        min_length=32,
        description="Django-style secret key for general signing",
    )
    API_V1_PREFIX: str = "/api/v1"

    # ── Authentication ─────────────────────────
    JWT_SECRET_KEY: str = Field(
        default="change-me",
        min_length=32,
        description="JWT signing key (must be strong in production)",
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ISSUER: str = "enterprise-rag"
    JWT_AUDIENCE: str = "enterprise-rag-api"

    # ── PostgreSQL ─────────────────────────────
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "rag_user"
    POSTGRES_PASSWORD: str = "rag_password"
    POSTGRES_DB: str = "enterprise_rag"
    POSTGRES_POOL_SIZE: int = 20
    POSTGRES_MAX_OVERFLOW: int = 40
    POSTGRES_ECHO: bool = False

    @property
    def database_url(self) -> str:
        """Build async PostgreSQL connection URL."""
        return str(
            PostgresDsn.build(
                scheme="postgresql+asyncpg",
                username=self.POSTGRES_USER,
                password=self.POSTGRES_PASSWORD,
                host=self.POSTGRES_HOST,
                port=self.POSTGRES_PORT,
                path=self.POSTGRES_DB,
            )
        )

    @property
    def database_url_sync(self) -> str:
        """Build sync PostgreSQL connection URL (for Alembic)."""
        return str(
            PostgresDsn.build(
                scheme="postgresql+psycopg2",
                username=self.POSTGRES_USER,
                password=self.POSTGRES_PASSWORD,
                host=self.POSTGRES_HOST,
                port=self.POSTGRES_PORT,
                path=self.POSTGRES_DB,
            )
        )

    # ── Redis ─────────────────────────────────
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0
    REDIS_SSL: bool = False
    REDIS_SOCKET_TIMEOUT: int = 5

    @property
    def redis_url(self) -> str:
        """Build Redis connection URL."""
        scheme = "rediss" if self.REDIS_SSL else "redis"
        auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"{scheme}://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # ── Vector Store ────────────────────────────
    VECTOR_STORE_PROVIDER: str = "milvus"
    VECTOR_STORE_DIMENSION: int = 4096  # nvidia/nv-embed-v1 produces 4096-dim vectors

    # ── Milvus ─────────────────────────────────
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 19530
    MILVUS_ALIAS: str = "default"
    MILVUS_USERNAME: str = ""
    MILVUS_PASSWORD: str = ""
    MILVUS_COLLECTION_PREFIX: str = "rag_"
    MILVUS_CONNECT_TIMEOUT: int = 10

    # ── Embedding Provider (new-style) ───────────
    EMBEDDING_PROVIDER: str = "nvidia_nim"
    NVIDIA_NIM_URL: HttpUrl = HttpUrl("https://integrate.api.nvidia.com/v1")  # type: ignore[assignment]
    NVIDIA_NIM_API_KEY: str = ""
    EMBEDDING_MODEL: str = "nvidia/nv-embed-v1"
    EMBEDDING_BATCH_SIZE: int = 32
    EMBEDDING_MAX_RETRIES: int = 3
    EMBEDDING_BACKOFF_MULTIPLIER: float = 2.0
    EMBEDDING_CACHE_ENABLED: bool = True
    EMBEDDING_CACHE_TTL_SECONDS: int = 86400

    # ── Indexing ────────────────────────────────
    INDEXING_BATCH_SIZE: int = 32
    INDEXING_MAX_CONCURRENT: int = 5
    INDEXING_MAX_RETRIES: int = 3
    INDEXING_MILVUS_BATCH_SIZE: int = 100
    INDEXING_DEFAULT_COLLECTION: str = "documents"

    # ── NVIDIA NIM (Hosted API — integrate.api.nvidia.com) ─
    # Embedding URL is base (code appends /embeddings). Rerank and chat are complete.
    NIM_EMBEDDING_URL: HttpUrl = HttpUrl("https://integrate.api.nvidia.com/v1")  # type: ignore[assignment]
    NIM_RERANKING_URL: HttpUrl = HttpUrl("https://integrate.api.nvidia.com/v1/rerank")  # type: ignore[assignment]
    NIM_CHAT_URL: HttpUrl = HttpUrl("https://integrate.api.nvidia.com/v1/chat/completions")  # type: ignore[assignment]
    NIM_API_KEY: str = ""
    NIM_MODEL_EMBEDDING: str = "nvidia/nv-embed-v1"
    NIM_MODEL_RERANK: str = "nvidia/nv-rerank-qa-4"
    NIM_MODEL_CHAT: str = "meta/llama-3.1-70b-instruct"
    NIM_TIMEOUT: int = 60

    # ── Rate Limiting ──────────────────────────
    MAX_CONCURRENT_REQUESTS: int = 10
    REQUEST_TIMEOUT: int = 30

    # ── Rate Limiting ──────────────────────────
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 60
    RATE_LIMIT_BURST: int = 100

    # ── CORS ──────────────────────────────────
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
    ]
    CORS_ALLOW_CREDENTIALS: bool = True

    # ── Logging ───────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: LogFormat = LogFormat.JSON
    LOG_FILE: str = "logs/rag-platform.log"

    # ── File Uploads ───────────────────────────
    MAX_UPLOAD_SIZE_MB: int = 100
    UPLOAD_DIR: str = "uploads"

    # ── Storage ────────────────────────────────
    STORAGE_PROVIDER: str = "local"
    STORAGE_ROOT: str = "uploads"
    STORAGE_TEMP_DIR: str = "uploads/temp"
    STORAGE_ALLOWED_EXTENSIONS: list[str] = [
        ".pdf",
        ".docx",
        ".pptx",
        ".xlsx",
        ".csv",
        ".md",
        ".html",
        ".htm",
        ".json",
        ".txt",
    ]

    # ── Evaluation ─────────────────────────────
    EVALUATION_ENABLED: bool = True
    GOLDEN_DATASET_PATH: Path = Path("./data/golden_dataset.json")

    # ── Monitoring ─────────────────────────────
    OTEL_SERVICE_NAME: str = "enterprise-rag"
    OTEL_EXPORTER_OTLP_ENDPOINT: HttpUrl = HttpUrl("http://localhost:4318")  # type: ignore[assignment]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        """Parse CORS origins from JSON string or list."""
        if isinstance(v, str):
            import json

            return json.loads(v)
        return v

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        """Ensure secrets are not defaults in production."""
        if self.ENVIRONMENT == Environment.PRODUCTION:
            if self.SECRET_KEY == "change-me":
                raise ValueError("SECRET_KEY must be changed from default in production")
            if self.JWT_SECRET_KEY == "change-me":
                raise ValueError("JWT_SECRET_KEY must be changed from default in production")
        return self


settings = Settings()
"""Global settings instance. Import this everywhere."""
