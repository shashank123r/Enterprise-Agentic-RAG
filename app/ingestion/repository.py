"""Database repository for the Enterprise Document Intelligence Pipeline."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.models import (
    Document,
    DocumentChunk,
    DocumentImage,
    DocumentTable,
    DocumentVersion,
    IngestionJob,
)
from app.repositories.base import BaseRepository


class DocumentRepository(BaseRepository[Document]):
    """Repository for Document CRUD and query operations."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, Document)

    async def get_by_checksum(self, checksum: str) -> Document | None:
        """Find a document by its content checksum."""
        stmt = select(Document).where(
            and_(Document.checksum == checksum, Document.is_deleted == False)  # noqa: E712
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_documents(
        self,
        page: int = 1,
        size: int = 20,
        status: str | None = None,
        user_id: str | None = None,
        include_deleted: bool = False,
    ) -> tuple[list[Document], int]:
        """List documents with pagination and optional filters."""
        conditions = [Document.is_deleted == include_deleted]
        if status:
            conditions.append(Document.status == status)
        if user_id:
            conditions.append(Document.user_id == user_id)

        count_stmt = select(func.count()).select_from(Document).where(and_(*conditions))
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0

        offset = (page - 1) * size
        fetch_stmt = (
            select(Document)
            .where(and_(*conditions))
            .order_by(Document.created_at.desc())
            .offset(offset)
            .limit(size)
        )
        result = await self.db.execute(fetch_stmt)
        return list(result.scalars().all()), total

    async def soft_delete(self, document_id: str) -> Document:
        """Soft delete a document."""
        return await self.update(document_id, is_deleted=True)

    async def hard_delete(self, document_id: str) -> None:
        """Permanently delete a document and all related data."""
        await self.delete(document_id)

    async def update_status(self, document_id: str, status: str, **extra: Any) -> Document:
        """Update document status."""
        return await self.update(document_id, status=status, **extra)


class DocumentVersionRepository(BaseRepository[DocumentVersion]):
    """Repository for DocumentVersion operations."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, DocumentVersion)

    async def get_versions(self, document_id: str) -> list[DocumentVersion]:
        """Get all versions for a document."""
        stmt = (
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_number.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_version(self, document_id: str) -> DocumentVersion | None:
        """Get the latest version of a document."""
        stmt = (
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_number.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_next_version_number(self, document_id: str) -> int:
        """Get the next version number for a document."""
        latest = await self.get_latest_version(document_id)
        return (latest.version_number + 1) if latest else 1


class DocumentChunkRepository(BaseRepository[DocumentChunk]):
    """Repository for DocumentChunk operations."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, DocumentChunk)

    async def get_chunks_by_document(self, document_id: str) -> list[DocumentChunk]:
        """Get all chunks for a document, ordered by position."""
        stmt = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def delete_by_document(self, document_id: str) -> None:
        """Delete all chunks for a document."""
        stmt = delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        await self.db.execute(stmt)
        await self.db.flush()

    async def bulk_create(self, chunks: list[dict[str, Any]]) -> list[DocumentChunk]:
        """Bulk insert chunks."""
        results: list[DocumentChunk] = []
        for chunk_data in chunks:
            chunk = DocumentChunk(**chunk_data)
            self.db.add(chunk)
            results.append(chunk)
        await self.db.flush()
        for chunk in results:
            await self.db.refresh(chunk)
        return results


class DocumentTableRepository(BaseRepository[DocumentTable]):
    """Repository for DocumentTable operations."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, DocumentTable)

    async def get_tables_by_document(self, document_id: str) -> list[DocumentTable]:
        stmt = (
            select(DocumentTable)
            .where(DocumentTable.document_id == document_id)
            .order_by(DocumentTable.table_index)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def delete_by_document(self, document_id: str) -> None:
        stmt = delete(DocumentTable).where(DocumentTable.document_id == document_id)
        await self.db.execute(stmt)
        await self.db.flush()


class DocumentImageRepository(BaseRepository[DocumentImage]):
    """Repository for DocumentImage operations."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, DocumentImage)

    async def get_images_by_document(self, document_id: str) -> list[DocumentImage]:
        stmt = (
            select(DocumentImage)
            .where(DocumentImage.document_id == document_id)
            .order_by(DocumentImage.image_index)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def delete_by_document(self, document_id: str) -> None:
        stmt = delete(DocumentImage).where(DocumentImage.document_id == document_id)
        await self.db.execute(stmt)
        await self.db.flush()


class IngestionJobRepository(BaseRepository[IngestionJob]):
    """Repository for IngestionJob operations."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, IngestionJob)

    async def get_active_jobs(self) -> list[IngestionJob]:
        """Get all jobs that are still processing."""
        stmt = (
            select(IngestionJob)
            .where(IngestionJob.status.in_(["queued", "processing"]))
            .order_by(IngestionJob.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_job_by_document(self, document_id: str) -> IngestionJob | None:
        """Get the most recent job for a document."""
        stmt = (
            select(IngestionJob)
            .where(IngestionJob.document_id == document_id)
            .order_by(IngestionJob.created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_progress(
        self,
        job_id: str,
        progress: float,
        current_stage: str | None = None,
    ) -> IngestionJob:
        """Update job progress percentage and current stage."""
        updates: dict[str, Any] = {"progress": progress}
        if current_stage:
            updates["current_stage"] = current_stage
        return await self.update(job_id, **updates)

    async def mark_started(self, job_id: str) -> IngestionJob:
        """Mark job as started processing."""
        return await self.update(
            job_id,
            status="processing",
            started_at=datetime.now(UTC),
        )

    async def mark_completed(self, job_id: str) -> IngestionJob:
        """Mark job as completed."""
        return await self.update(
            job_id,
            status="completed",
            progress=100.0,
            current_stage="completed",
            completed_at=datetime.now(UTC),
        )

    async def mark_failed(self, job_id: str, error_message: str) -> IngestionJob:
        """Mark job as failed with error details."""
        return await self.update(
            job_id,
            status="failed",
            current_stage="failed",
            error_message=error_message,
        )

    async def mark_retrying(self, job_id: str, retry_count: int) -> IngestionJob:
        """Mark job for retry."""
        return await self.update(
            job_id,
            status="retrying",
            retry_count=retry_count,
        )

    async def mark_cancelled(self, job_id: str) -> IngestionJob:
        """Mark job as cancelled."""
        return await self.update(
            job_id,
            status="cancelled",
            current_stage="cancelled",
        )
