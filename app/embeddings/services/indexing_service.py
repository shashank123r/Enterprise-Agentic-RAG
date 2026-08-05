"""Enterprise Indexing Service — orchestrates the full indexing pipeline.

Responsibilities:
  - Start, cancel, retry, and rebuild indexing operations.
  - Orchestrate chunk retrieval → cache → embed → vector store persistence.
  - Track job lifecycle with checkpoint-based crash recovery.
  - Support incremental (delta) and full re-indexing.
  - Support ARQ-based durable background processing.

Business logic lives here. Provider specifics stay in EmbeddingProvider.
Milvus specifics stay in VectorStore.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.embeddings.cache import EmbeddingCacheService
from app.embeddings.providers.base import EmbeddingProvider
from app.embeddings.services.batch_indexer import BatchIndexer
from app.embeddings.services.task_manager import TaskManager
from app.models.indexing_job import IndexingJob
from app.repositories.indexing_job_repository import IndexingJobRepository
from app.vector_stores.base import VectorStore
from app.vector_stores.collection_manager import CollectionManager
from app.vector_stores.exceptions import CollectionNotFound

logger = get_logger(__name__)

# Application-scoped globals — initialized once in the FastAPI lifespan.
# This ensures _active_jobs is shared across all requests (fixes C2).
_indexing_service_instance: IndexingService | None = None
_task_manager_instance: TaskManager | None = None


def get_indexing_service_instance() -> IndexingService:
    """Get the application-scoped IndexingService singleton.

    Raises:
        RuntimeError: If the service has not been initialized during lifespan.
    """
    if _indexing_service_instance is None:
        raise RuntimeError(
            "IndexingService not initialized. "
            "Call init_indexing_service() during application lifespan startup."
        )
    return _indexing_service_instance


def get_task_manager_instance() -> TaskManager:
    """Get the application-scoped TaskManager singleton."""
    global _task_manager_instance
    if _task_manager_instance is None:
        _task_manager_instance = TaskManager()
    return _task_manager_instance


async def init_indexing_service(
    embedding_provider: EmbeddingProvider,
    vector_store: VectorStore,
    collection_manager: CollectionManager,
) -> None:
    """Initialize the application-scoped IndexingService singleton.

    Called during FastAPI lifespan startup. After this, any component
    can use get_indexing_service_instance() to access the shared service.
    """
    global _indexing_service_instance, _task_manager_instance
    _task_manager_instance = TaskManager()
    _indexing_service_instance = IndexingService(
        embedding_provider=embedding_provider,
        vector_store=vector_store,
        collection_manager=collection_manager,
    )
    logger.info("IndexingService initialized as application-scoped singleton")


async def shutdown_indexing_service() -> None:
    """Shut down the IndexingService and its task manager.

    Called during FastAPI lifespan shutdown.
    """
    global _indexing_service_instance, _task_manager_instance
    if _task_manager_instance is not None:
        await _task_manager_instance.shutdown(timeout=30.0)
        _task_manager_instance = None
    _indexing_service_instance = None
    logger.info("IndexingService shut down")


class IndexingService:
    """Orchestrates the end-to-end indexing pipeline.

    This is an application-scoped singleton (not per-request) so that
    ``_active_jobs`` and task tracking are shared across all API requests.
    This makes job cancellation actually work (fixes C2).

    Usage:
        service = IndexingService(
            embedding_provider=provider,
            vector_store=store,
            collection_manager=manager,
            cache=cache,
        )

        # Start a new indexing job
        job = await service.start_indexing(
            db=db_session,
            document_id="doc-123",
            chunks=[...],
            collection_name="documents",
        )
    """

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
        collection_manager: CollectionManager,
        cache: EmbeddingCacheService | None = None,
        batch_size: int = 32,
        max_concurrent: int = 5,
        max_retries: int = 3,
    ) -> None:
        self._provider = embedding_provider
        self._store = vector_store
        self._collection_manager = collection_manager
        self._cache = cache or EmbeddingCacheService()
        self._batch_size = batch_size
        self._max_concurrent = max_concurrent
        self._max_retries = max_retries
        self._task_manager = get_task_manager_instance()

    # ── Public API ─────────────────────────────

    async def start_indexing(
        self,
        db: AsyncSession,
        document_id: str,
        chunks: list[dict[str, Any]],
        collection_name: str,
        use_arq: bool = False,
        embedding_model: str | None = None,
        vector_dimension: int | None = None,
    ) -> IndexingJob:
        """Start a new indexing job.

        1. Ensures the target collection exists.
        2. Creates a job record in ``queued`` status.
        3. Runs the indexing pipeline (background via TaskManager or ARQ).

        Args:
            db: Database session.
            document_id: Document UUID to index.
            chunks: List of chunk dicts with text, metadata, checksum, etc.
            collection_name: Target Milvus collection name.
            use_arq: If True, enqueue via ARQ for durable processing.
            embedding_model: Embedding model name. Uses config default.
            vector_dimension: Vector dimension. Uses config default.

        Returns:
            The created IndexingJob.
        """
        model = embedding_model or settings.EMBEDDING_MODEL
        dim = vector_dimension or settings.VECTOR_STORE_DIMENSION

        # Ensure collection exists
        await self._collection_manager.create(
            collection_name,
            dimension=dim,
            if_not_exists=True,
        )

        # Create job record
        repo = IndexingJobRepository(db)
        job = await repo.create_job(
            document_id=document_id,
            collection_name=collection_name,
            total_chunks=len(chunks),
            max_retries=self._max_retries,
            embedding_model=model,
            vector_dimension=dim,
        )

        if use_arq:
            # ARQ-based: enqueue for durable background processing
            # The ARQ worker picks this up and runs the pipeline
            await self._enqueue_arq_job(job.id, document_id, collection_name)
        else:
            # In-process: use TaskManager for tracked background execution
            await self._task_manager.create_task(
                job.id,
                self._run_indexing(
                    job_id=job.id,
                    chunks=chunks,
                    collection_name=collection_name,
                ),
                name=f"indexing:{document_id[:12]}",
            )

        return job

    async def cancel_indexing(self, job_id: str, repo: IndexingJobRepository) -> IndexingJob:
        """Cancel an active indexing job.

        Signals the background task (in-process or ARQ) and updates DB.
        The DB status transition is handled inside ``_run_indexing``.

        Args:
            job_id: Job UUID.
            repo: IndexingJobRepository for DB operations.

        Returns:
            The IndexingJob (status updated when background task completes).

        Raises:
            ValueError: If the job doesn't exist.
        """
        # Cancel the in-process task if it exists
        await self._task_manager.cancel_task(job_id)

        # Also mark as cancelled in DB
        job = await repo.cancel_job(job_id)
        if job is None:
            raise ValueError(f"Job not found: {job_id}")

        logger.info(
            "Cancellation requested for indexing job",
            job_id=job_id,
            document_id=job.document_id,
            current_status=job.status,
        )
        return job

    async def retry_indexing(
        self,
        job_id: str,
        db: AsyncSession,
        chunks: list[dict[str, Any]],
    ) -> IndexingJob:
        """Retry a failed indexing job.

        Resets the job to ``queued`` and re-runs with the stored checkpoint.

        Args:
            job_id: Job UUID.
            db: Database session.
            chunks: Chunks to re-index.

        Returns:
            The re-queued IndexingJob.
        """
        repo = IndexingJobRepository(db)
        job = await repo.reset_job_for_retry(job_id)
        if job is None:
            raise ValueError(f"Job not found or not retryable: {job_id}")

        # Re-run via TaskManager
        await self._task_manager.create_task(
            job_id,
            self._run_indexing(
                job_id=job_id,
                chunks=chunks,
                collection_name=job.collection_name,
            ),
            name=f"retry:{job.document_id[:12]}",
        )

        logger.info(
            "Retrying indexing job",
            job_id=job_id,
            document_id=job.document_id,
            retry_count=job.retry_count,
        )
        return job

    @staticmethod
    async def get_job_status(job_id: str, repo: IndexingJobRepository) -> IndexingJob | None:
        """Get the current status of an indexing job."""
        return await repo.get_by_id(job_id)

    @staticmethod
    async def list_jobs(
        repo: IndexingJobRepository,
        document_id: str | None = None,
        limit: int = 20,
    ) -> list[IndexingJob]:
        """List indexing jobs, optionally filtered by document."""
        if document_id:
            return await repo.get_jobs_by_document(document_id, limit=limit)
        return await repo.list_all(limit=limit, order_by="created_at")

    async def delete_document_index(
        self,
        document_id: str,
        collection_name: str,
    ) -> int:
        """Delete all vectors for a document from the vector store.

        Args:
            document_id: Document UUID to delete.
            collection_name: Target collection.

        Returns:
            Number of vectors deleted (approximate).
        """
        try:
            deleted = await self._store.delete_vectors(
                collection_name,
                filter_expr=f'document_id == "{document_id}"',
            )
            logger.info(
                "Deleted document index",
                document_id=document_id,
                collection=collection_name,
                deleted=deleted,
            )
            return deleted
        except CollectionNotFound:
            logger.warning("Collection not found for deletion", collection=collection_name)
            return 0

    async def rebuild_document_index(
        self,
        db: AsyncSession,
        document_id: str,
        chunks: list[dict[str, Any]],
        collection_name: str,
        use_arq: bool = False,
        embedding_model: str | None = None,
    ) -> IndexingJob:
        """Delete existing index and re-index a document.

        Performs atomic delete-then-index.

        Args:
            db: Database session.
            document_id: Document UUID.
            chunks: Chunks to index.
            collection_name: Target collection.
            use_arq: If True, enqueue via ARQ for durable processing.
            embedding_model: Optional embedding model override.

        Returns:
            The new IndexingJob.
        """
        await self.delete_document_index(document_id, collection_name)

        # Invalidate cache for this document's chunks
        checksums = [c.get("checksum", "") for c in chunks if c.get("checksum")]
        if checksums and self._cache is not None:
            await self._cache.invalidate_document(checksums)

        return await self.start_indexing(
            db=db,
            document_id=document_id,
            chunks=chunks,
            collection_name=collection_name,
            use_arq=use_arq,
            embedding_model=embedding_model,
        )

    @staticmethod
    async def get_job_counts_by_status(repo: IndexingJobRepository) -> dict[str, int]:
        """Get indexing job counts grouped by status."""
        return await repo.count_by_status()

    @staticmethod
    async def get_active_jobs_list(repo: IndexingJobRepository) -> list[IndexingJob]:
        """Get all currently active indexing jobs."""
        return await repo.get_active_jobs()

    async def health_check_embedding(self) -> dict[str, Any]:
        """Check embedding provider health.

        Returns:
            Dict with 'healthy', 'provider', 'model', 'latency_ms'.
        """
        import time

        start = time.monotonic()
        healthy = await self._provider.health_check()
        latency_ms = (time.monotonic() - start) * 1000
        return {
            "healthy": healthy,
            "provider": self._provider.provider_name(),
            "model": settings.EMBEDDING_MODEL,
            "latency_ms": round(latency_ms, 2),
        }

    async def health_check_vector_store(self) -> dict[str, Any]:
        """Check vector store health.

        Returns:
            Dict with 'healthy', 'provider', 'collections'.
        """
        healthy = await self._store.health_check()
        collections = []
        if healthy:
            try:
                collections = await self._store.list_collections()
            except Exception:
                pass
        return {
            "healthy": healthy,
            "provider": settings.VECTOR_STORE_PROVIDER,
            "collections_count": len(collections),
            "collections": collections[:20],
        }

    async def health_check_indexing(self) -> dict[str, Any]:
        """Get aggregate indexing health.

        Returns:
            Dict with active jobs, task manager status.
        """
        active_count = await self._task_manager.active_count()
        return {
            "task_manager_active_tasks": active_count,
            "use_arq": False,
        }

    # ── Internal Pipeline ──────────────────────

    async def _enqueue_arq_job(
        self,
        job_id: str,
        document_id: str,
        collection_name: str,
    ) -> None:
        """Enqueue an indexing job for the ARQ worker using ARQ's proper API.

        Uses arq.create_pool().enqueue_job() for correct serialization.

        Args:
            job_id: Job UUID.
            document_id: Document UUID.
            collection_name: Target collection.
        """
        try:
            from arq import create_pool

            pool = await create_pool(settings.redis_url)
            await pool.enqueue_job(
                "index_document",
                job_id,
                document_id,
                collection_name,
            )
            logger.info(
                "Enqueued indexing job for ARQ worker",
                job_id=job_id,
                document_id=document_id,
            )
        except Exception as e:
            logger.error("Failed to enqueue ARQ indexing job", error=str(e))
            raise

    async def _run_indexing(
        self,
        job_id: str,
        chunks: list[dict[str, Any]],
        collection_name: str,
    ) -> dict[str, Any]:
        """Execute the indexing pipeline for a job.

        Creates its own DB session because this runs as a background
        task that outlives the HTTP request.

        1. Creates a DB session.
        2. Transition job to ``processing``.
        3. Run batch indexer.
        4. Transition job to ``completed`` or ``failed``.

        Args:
            job_id: Job UUID.
            chunks: Chunks to index.
            collection_name: Target collection.

        Returns:
            Result dict from batch indexer.
        """
        repo: IndexingJobRepository | None = None
        async with async_session_factory() as db:
            repo = IndexingJobRepository(db)
            cancel_event = await self._task_manager.get_cancel_event(job_id)

            try:
                # Transition to processing
                job = await repo.transition_status(job_id, "processing")
                if job is None:
                    logger.error("Job not found for processing", job_id=job_id)
                    return {"indexed": 0, "failed": 0, "cancelled": False}

                total = job.total_chunks or len(chunks)

                # Check for checkpoint resume
                resume_from = 0
                if job.checkpoint:
                    resume_from = job.checkpoint.get("processed_chunks", 0)
                    logger.info("Resuming from checkpoint", job_id=job_id, checkpoint=resume_from)

                # Progress callback
                async def _on_progress(processed: int, total: int, failed: int) -> None:
                    try:
                        await repo.update_progress(
                            job_id,
                            processed_chunks=processed,
                            total_chunks=total,
                            failed_chunks=failed,
                            checkpoint={"processed_chunks": processed},
                        )
                    except Exception as e:
                        logger.warning("Progress update failed", error=str(e))

                # Run batch indexer
                indexer = BatchIndexer(
                    embedding_provider=self._provider,
                    vector_store=self._store,
                    cache=self._cache,
                )

                cache_hits: list[int] = []
                result = await indexer.index_chunks(
                    collection_name=collection_name,
                    chunks=chunks[resume_from:] if resume_from else chunks,
                    document_id=job.document_id,
                    cache_hits=cache_hits,
                    progress_callback=_on_progress,
                    cancel_event=cancel_event,
                )

                if result.get("cancelled"):
                    await repo.transition_status(job_id, "cancelled")
                    return result

                # Record metrics
                await repo.record_metrics(
                    job_id,
                    cache_hits=len(cache_hits),
                    total_duration_ms=result.get("duration_ms"),
                )

                # Final status
                if result.get("failed", 0) > 0 and result.get("indexed", 0) == 0:
                    await repo.record_failure(
                        job_id,
                        error_message=f"All {result['failed']} chunks failed to index",
                        increment_retry=True,
                    )
                else:
                    await repo.transition_status(job_id, "completed")

                logger.info(
                    "Indexing job completed",
                    job_id=job_id,
                    indexed=result.get("indexed"),
                    failed=result.get("failed"),
                    cache_hits=len(cache_hits),
                )

                return result

            except asyncio.CancelledError:
                if repo:
                    await repo.transition_status(job_id, "cancelled")
                logger.warning("Indexing job cancelled", job_id=job_id)
                raise

            except Exception as e:
                logger.error("Indexing job failed", job_id=job_id, error=str(e))
                if repo:
                    try:
                        await repo.record_failure(
                            job_id,
                            error_message=str(e),
                            increment_retry=True,
                        )
                    except Exception as repo_e:
                        logger.error("Failed to record job failure", error=str(repo_e))
                return {"indexed": 0, "failed": 0, "cancelled": False}

            finally:
                # CRITICAL: Commit all status transitions and progress updates.
                # Without this, all DB changes are rolled back when the session
                # context manager exits (async_session_factory closes without commit).
                try:
                    await db.commit()
                except Exception as commit_e:
                    logger.error("Failed to commit indexing job changes", error=str(commit_e))

    async def _run_indexing_pipeline(
        self,
        job_id: str,
        chunks: list[dict[str, Any]],
        collection_name: str,
    ) -> dict[str, Any]:
        """Run the indexing pipeline directly (for ARQ worker usage).

        This is the same as _run_indexing but doesn't create a DB session
        (the ARQ worker provides its own session).

        Args:
            job_id: Job UUID.
            chunks: Chunks to index.
            collection_name: Target collection.

        Returns:
            Result dict from batch indexer.
        """
        # This method is called from the ARQ worker which already has a DB session.
        # The actual pipeline execution is delegated.
        from app.core.config import settings

        indexer = BatchIndexer(
            embedding_provider=self._provider,
            vector_store=self._store,
            cache=self._cache,
        )

        result = await indexer.index_chunks(
            collection_name=collection_name,
            chunks=chunks,
            document_id=job_id,
        )

        return result


from app.db.session import async_session_factory  # noqa: E402, F811
