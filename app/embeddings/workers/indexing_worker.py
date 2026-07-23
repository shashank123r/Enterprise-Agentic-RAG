"""ARQ background worker for vector indexing jobs.

Replaces ephemeral asyncio.create_task() with durable queue-based
processing. Jobs survive application restarts and can be retried,
cancelled, or resumed via the queue.

Run with:
    arq app.embeddings.workers.indexing_worker.WorkerSettings
"""

from __future__ import annotations

from typing import Any

from arq import create_pool

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import async_session_factory
from app.embeddings.cache import EmbeddingCacheService
from app.embeddings.providers.factory import get_embedding_provider
from app.embeddings.services.indexing_service import IndexingService
from app.ingestion.repository import DocumentChunkRepository
from app.repositories.indexing_job_repository import IndexingJobRepository
from app.vector_stores.factory import get_vector_store, get_collection_manager

logger = get_logger(__name__)

INDEXING_DLQ_KEY = "rag:dlq:indexing"
MAX_RETRIES = 3


async def index_document(ctx: dict[str, Any], job_id: str, document_id: str, collection_name: str) -> dict[str, Any]:
    """Background ARQ task: index a document's chunks into the vector store.

    This task is enqueued by the API after creating the IndexingJob record.
    The ARQ worker handles retries automatically (configurable via WorkerSettings).

    Args:
        ctx: ARQ context.
        job_id: IndexingJob UUID to track progress against.
        document_id: Document UUID whose chunks should be indexed.
        collection_name: Target Milvus collection name.

    Returns:
        Stats dict with indexed/failed counts.

    Raises:
        Exception: On failure — ARQ handles retries automatically.
    """
    logger.info("ARQ indexing task started", job_id=job_id, document_id=document_id)

    async with async_session_factory() as db:
        # Load chunks from ingestion repository
        chunk_repo = DocumentChunkRepository(db)
        chunks = await chunk_repo.get_chunks_by_document(document_id)

        if not chunks:
            logger.warning("No chunks found for document", document_id=document_id)
            return {"indexed": 0, "failed": 0, "cache_hits": 0, "duration_ms": 0}

        # Convert ORM chunks to dict format
        chunk_dicts = []
        for c in chunks:
            meta = dict(c.metadata) if c.metadata else {}
            meta["document_id"] = document_id
            chunk_dicts.append({
                "chunk_id": c.id,
                "text": c.content,
                "metadata": meta,
                "checksum": c.content_checksum,
                "chunk_index": c.chunk_index,
                "page_number": c.page_number,
                "section_title": c.section_title,
                "language": c.language or "unknown",
                "version": 1,
                "source": "",
            })

        # Get singletons
        provider = await get_embedding_provider()
        store = None
        manager = None
        async for s in get_vector_store():
            store = s
            break
        async for m in get_collection_manager():
            manager = m
            break

        cache = EmbeddingCacheService()

        # Create IndexingService — no `db` parameter, constructor doesn't accept one
        service = IndexingService(
            embedding_provider=provider,
            vector_store=store,
            collection_manager=manager,
            cache=cache,
        )

        # Ensure collection exists
        dim = settings.VECTOR_STORE_DIMENSION
        await manager.create(collection_name, dimension=dim, if_not_exists=True)

        # Transition job to processing
        repo = IndexingJobRepository(db)
        job = await repo.transition_status(job_id, "processing")
        if job is None:
            logger.error("ARQ job not found", job_id=job_id)
            return {"indexed": 0, "failed": 0, "error": "job_not_found"}

        try:
            # Run the batch indexer directly (same as _run_indexing but in ARQ context)
            from app.embeddings.services.batch_indexer import BatchIndexer
            indexer = BatchIndexer(
                embedding_provider=provider,
                vector_store=store,
                cache=cache,
            )

            result = await indexer.index_chunks(
                collection_name=collection_name,
                chunks=chunk_dicts,
                document_id=document_id,
            )

            # Update job status based on results
            if result.get("cancelled"):
                await repo.transition_status(job_id, "cancelled")
            elif result.get("failed", 0) > 0 and result.get("indexed", 0) == 0:
                await repo.record_failure(
                    job_id,
                    error_message=f"All {result['failed']} chunks failed to index",
                    increment_retry=True,
                )
            else:
                await repo.transition_status(job_id, "completed")

            logger.info(
                "ARQ indexing task completed",
                job_id=job_id,
                **result,
            )
            return result

        except Exception as e:
            logger.exception("ARQ indexing task failed", job_id=job_id, error=str(e))
            await repo.record_failure(
                job_id,
                error_message=str(e),
                increment_retry=True,
            )
            raise  # Let ARQ handle retry


async def cleanup_indexing_job(ctx: dict[str, Any], job_id: str) -> bool:
    """Clean up an indexing job's queue artifacts.

    Args:
        ctx: ARQ context.
        job_id: Job UUID to clean up.

    Returns:
        True if cleanup succeeded.
    """
    redis = ctx.get("redis")
    if redis:
        await redis.delete(f"rag:retry_count:indexing:{job_id}")
    logger.info("Cleaned up indexing job artifacts", job_id=job_id)
    return True


async def retry_dead_letter_indexing(ctx: dict[str, Any]) -> int:
    """Re-process indexing jobs from the dead-letter queue.

    Returns:
        Number of jobs re-queued.
    """
    redis = ctx.get("redis")
    if not redis:
        return 0

    count = 0
    while True:
        item = await redis.rpop(INDEXING_DLQ_KEY)
        if not item:
            break

        parts = item.split(":")
        if len(parts) >= 3:
            job_id, document_id, collection_name = parts[0], parts[1], parts[2]
            pool = await create_pool(
                settings.redis_url,
            )
            await pool.enqueue_job(
                "index_document",
                job_id,
                document_id,
                collection_name,
            )
            count += 1

    if count:
        logger.info("Re-queued indexing jobs from dead-letter queue", count=count)
    return count


async def _worker_startup(ctx: dict) -> None:
    """Initialize resources when the ARQ worker starts."""
    from app.core.logging import setup_logging
    setup_logging()
    logger.info(
        "Indexing ARQ worker started",
        redis_host=settings.REDIS_HOST,
        redis_port=settings.REDIS_PORT,
    )


async def _worker_shutdown(ctx: dict) -> None:
    """Clean up when the ARQ worker stops."""
    logger.info("Indexing ARQ worker shutting down")


class WorkerSettings:
    """ARQ worker configuration for background indexing.

    Usage:
        arq app.embeddings.workers.indexing_worker.WorkerSettings
    """

    functions = [index_document, cleanup_indexing_job, retry_dead_letter_indexing]
    redis_settings = {
        "host": settings.REDIS_HOST,
        "port": settings.REDIS_PORT,
        "password": settings.REDIS_PASSWORD or None,
        "database": settings.REDIS_DB,
    }
    max_tries = MAX_RETRIES
    max_burst_jobs = 5
    job_timeout = 600  # 10 minutes max per job
    keep_result_seconds = 86400
    keep_result_hours = 24
    poll_delay = 1.0
    on_startup = _worker_startup
    on_shutdown = _worker_shutdown
