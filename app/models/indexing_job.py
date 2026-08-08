"""IndexingJob ORM model — tracks every indexing operation through its lifecycle.

Statuses: queued → processing → embedding → writing → completed
                                         ├── cancelled
                                         └── failed (→ retrying → processing)
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class IndexingJob(Base, UUIDMixin, TimestampMixin):
    """Tracks a single indexing operation from start to completion."""

    __tablename__ = "indexing_jobs"

    # ── Job identity ──────────────────────────
    document_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        index=True,
        nullable=False,
        comment="The document being indexed",
    )
    collection_name: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
        comment="Target Milvus collection name",
    )

    # ── Status lifecycle ──────────────────────
    status: Mapped[str] = mapped_column(
        String(32),
        default="queued",
        index=True,
        nullable=False,
        comment="queued | processing | embedding | writing | completed | failed | cancelled | retrying",
    )

    # ── Progress tracking ─────────────────────
    total_chunks: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    processed_chunks: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    failed_chunks: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    progress_percent: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )

    # ── Metrics ───────────────────────────────
    embedding_latency_ms: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    vector_store_latency_ms: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    total_duration_ms: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    cache_hits: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # ─── Checkpoint ───────────────────────────
    checkpoint: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Serialised checkpoint for resume-after-crash recovery",
    )

    # ── Error handling ────────────────────────
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    error_details: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    retry_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    max_retries: Mapped[int] = mapped_column(
        Integer,
        default=3,
        nullable=False,
    )

    # ── Timing ────────────────────────────────
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ── Embedding metadata ────────────────────
    embedding_model: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    vector_dimension: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<IndexingJob(id={self.id}, document_id={self.document_id}, "
            f"status={self.status}, progress={self.progress_percent:.1f}%)>"
        )
