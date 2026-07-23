"""Add embedding indexing_jobs table for tracking vector indexing lifecycle.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "indexing_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=False), nullable=False, index=True),
        sa.Column("collection_name", sa.String(256), nullable=False),
        sa.Column(
            "status", sa.String(32), nullable=False, server_default="queued", index=True,
            comment="queued | processing | embedding | writing | completed | failed | cancelled | retrying",
        ),
        sa.Column("total_chunks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("processed_chunks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_chunks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("progress_percent", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("embedding_latency_ms", sa.Float(), nullable=True),
        sa.Column("vector_store_latency_ms", sa.Float(), nullable=True),
        sa.Column("total_duration_ms", sa.Float(), nullable=True),
        sa.Column("cache_hits", sa.Integer(), server_default="0", nullable=False),
        sa.Column("checkpoint", postgresql.JSONB(), nullable=True,
                  comment="Serialised checkpoint for resume-after-crash recovery"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_details", postgresql.JSONB(), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_retries", sa.Integer(), server_default="3", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("embedding_model", sa.String(128), nullable=True),
        sa.Column("vector_dimension", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_indexing_jobs_document_status", "indexing_jobs", ["document_id", "status"])
    op.create_index("ix_indexing_jobs_status_created", "indexing_jobs", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_indexing_jobs_status_created", table_name="indexing_jobs")
    op.drop_index("ix_indexing_jobs_document_status", table_name="indexing_jobs")
    op.drop_table("indexing_jobs")
