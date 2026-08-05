"""IndexingJob repository — database operations for indexing job tracking.

Supports full CRUD, atomic status transitions, checkpoint persistence,
progress updates, and querying active/failed/retryable jobs.
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.indexing_job import IndexingJob
from app.repositories.base import BaseRepository

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"processing", "cancelled"},
    "processing": {"embedding", "writing", "completed", "failed", "cancelled"},
    "embedding": {"writing", "completed", "failed", "cancelled"},
    "writing": {"completed", "failed", "cancelled"},
    "failed": {"retrying", "cancelled"},
    "retrying": {"processing", "failed", "cancelled"},
    "cancelled": set(),
    "completed": set(),
}


class IndexingJobRepository(BaseRepository[IndexingJob]):
    """Repository for indexing job CRUD and lifecycle management."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, IndexingJob)

    async def create_job(
        self,
        document_id: str,
        collection_name: str,
        total_chunks: int = 0,
        max_retries: int = 3,
        embedding_model: str | None = None,
        vector_dimension: int | None = None,
    ) -> IndexingJob:
        """Create a new indexing job in queued status."""
        return await self.create(
            document_id=document_id,
            collection_name=collection_name,
            total_chunks=total_chunks,
            max_retries=max_retries,
            embedding_model=embedding_model,
            vector_dimension=vector_dimension,
            status="queued",
        )

    async def transition_status(
        self,
        job_id: str,
        new_status: str,
    ) -> IndexingJob | None:
        """Atomically transition a job's status.

        Validates the transition against allowed state machine rules.
        Returns None if the job doesn't exist.

        Raises:
            ValueError: If the transition is not allowed.
        """
        job = await self.get_by_id(job_id)
        if job is None:
            return None

        allowed = _ALLOWED_TRANSITIONS.get(job.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Invalid status transition: {job.status} → {new_status}. " f"Allowed: {allowed}"
            )

        update_values: dict[str, Any] = {"status": new_status}

        now = datetime.now(timezone.utc)
        if new_status == "processing" and job.started_at is None:
            update_values["started_at"] = now
        if new_status == "completed":
            update_values["completed_at"] = now
            update_values["progress_percent"] = 100.0

        stmt = (
            update(IndexingJob)
            .where(IndexingJob.id == job_id)
            .values(**update_values)
            .returning(IndexingJob)
        )
        result = await self.db.execute(stmt)
        await self.db.flush()
        return result.scalar_one_or_none()

    async def update_progress(
        self,
        job_id: str,
        processed_chunks: int,
        total_chunks: int | None = None,
        failed_chunks: int | None = None,
        checkpoint: dict[str, Any] | None = None,
    ) -> IndexingJob | None:
        """Update a job's progress and optional checkpoint.

        Args:
            job_id: Job UUID.
            processed_chunks: Number of chunks processed so far.
            total_chunks: If provided, update total chunk count.
            failed_chunks: If provided, update failed chunk count.
            checkpoint: Optional serialised checkpoint for resume recovery.

        Returns:
            Updated job or None if not found.
        """
        update_values: dict[str, Any] = {
            "processed_chunks": processed_chunks,
            "progress_percent": 0.0,
        }

        if total_chunks is not None:
            update_values["total_chunks"] = total_chunks

        if failed_chunks is not None:
            update_values["failed_chunks"] = failed_chunks

        if checkpoint is not None:
            update_values["checkpoint"] = checkpoint

        job = await self.get_by_id(job_id)
        if job is None:
            return None

        total = total_chunks if total_chunks is not None else job.total_chunks
        if total > 0:
            update_values["progress_percent"] = round((processed_chunks / total) * 100, 1)

        stmt = (
            update(IndexingJob)
            .where(IndexingJob.id == job_id)
            .values(**update_values)
            .returning(IndexingJob)
        )
        result = await self.db.execute(stmt)
        await self.db.flush()
        return result.scalar_one_or_none()

    async def record_failure(
        self,
        job_id: str,
        error_message: str,
        error_details: dict[str, Any] | None = None,
        increment_retry: bool = True,
    ) -> IndexingJob | None:
        """Record a failure and determine next status.

        If retries remain, transitions to 'retrying'.
        If max retries exceeded, transitions to 'failed'.

        Args:
            job_id: Job UUID.
            error_message: Human-readable error description.
            error_details: Optional structured error data.
            increment_retry: If True, increments retry_count.

        Returns:
            Updated job or None if not found.
        """
        job = await self.get_by_id(job_id)
        if job is None:
            return None

        new_retry_count = job.retry_count + 1 if increment_retry else job.retry_count
        has_retries_left = new_retry_count < job.max_retries

        new_status = "retrying" if has_retries_left else "failed"

        update_values: dict[str, Any] = {
            "status": new_status,
            "error_message": error_message,
            "retry_count": new_retry_count,
        }
        if error_details:
            update_values["error_details"] = error_details

        if not has_retries_left:
            update_values["completed_at"] = datetime.now(timezone.utc)

        stmt = (
            update(IndexingJob)
            .where(IndexingJob.id == job_id)
            .values(**update_values)
            .returning(IndexingJob)
        )
        result = await self.db.execute(stmt)
        await self.db.flush()
        return result.scalar_one_or_none()

    async def record_metrics(
        self,
        job_id: str,
        embedding_latency_ms: float | None = None,
        vector_store_latency_ms: float | None = None,
        total_duration_ms: float | None = None,
        cache_hits: int | None = None,
    ) -> None:
        """Record performance metrics for a job."""
        update_values: dict[str, Any] = {}
        if embedding_latency_ms is not None:
            update_values["embedding_latency_ms"] = embedding_latency_ms
        if vector_store_latency_ms is not None:
            update_values["vector_store_latency_ms"] = vector_store_latency_ms
        if total_duration_ms is not None:
            update_values["total_duration_ms"] = total_duration_ms
        if cache_hits is not None:
            update_values["cache_hits"] = cache_hits

        if update_values:
            stmt = update(IndexingJob).where(IndexingJob.id == job_id).values(**update_values)
            await self.db.execute(stmt)
            await self.db.flush()

    async def get_active_jobs(self) -> list[IndexingJob]:
        """Get all jobs that are currently active (queued, processing, retrying)."""
        stmt = (
            select(IndexingJob)
            .where(IndexingJob.status.in_(["queued", "processing", "retrying"]))
            .order_by(IndexingJob.created_at.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_retryable_jobs(self) -> list[IndexingJob]:
        """Get all jobs in 'retrying' status that can be retried."""
        stmt = (
            select(IndexingJob)
            .where(IndexingJob.status == "retrying")
            .order_by(IndexingJob.retry_count.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_jobs_by_document(
        self,
        document_id: str,
        limit: int = 20,
    ) -> list[IndexingJob]:
        """Get all indexing jobs for a given document, newest first."""
        stmt = (
            select(IndexingJob)
            .where(IndexingJob.document_id == document_id)
            .order_by(IndexingJob.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def cancel_job(self, job_id: str) -> IndexingJob | None:
        """Cancel a job (only if it's not already completed or cancelled)."""
        return await self.transition_status(job_id, "cancelled")

    async def reset_job_for_retry(
        self,
        job_id: str,
    ) -> IndexingJob | None:
        """Reset a retrying job back to queued for re-processing."""
        job = await self.get_by_id(job_id)
        if job is None:
            return None
        if job.status != "retrying":
            raise ValueError(f"Cannot reset job in status '{job.status}' to queued")

        stmt = (
            update(IndexingJob)
            .where(IndexingJob.id == job_id)
            .values(
                status="queued",
                checkpoint=None,
                error_message=None,
                error_details=None,
                started_at=None,
            )
            .returning(IndexingJob)
        )
        result = await self.db.execute(stmt)
        await self.db.flush()
        return result.scalar_one_or_none()

    async def count_by_status(self) -> dict[str, int]:
        """Get job counts grouped by status."""
        from sqlalchemy import func

        stmt = select(IndexingJob.status, func.count(IndexingJob.id)).group_by(IndexingJob.status)
        result = await self.db.execute(stmt)
        return dict(result.all())
