"""ARQ background task definitions for document ingestion.

Handles queued ingestion jobs with retry logic, progress tracking,
and dead-letter queue support.
"""

from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import async_session_factory
from app.storage.factory import get_storage_provider

logger = get_logger(__name__)

MAX_RETRIES = 3
DLQ_KEY = "rag:dlq:ingestion"


async def process_document(
    ctx: dict[str, Any], document_id: str, file_path: str, mime_type: str, user_id: str
) -> dict[str, Any]:
    """Process a document through the ingestion pipeline.

    This is the main ARQ task. Called by the worker when a job is dequeued.

    Args:
        ctx: ARQ context (includes redis connection).
        document_id: UUID of the document to process.
        file_path: Storage path of the uploaded file.
        mime_type: Detected MIME type.
        user_id: Uploading user ID.

    Returns:
        Stats dict from the ingestion pipeline.
    """
    from app.ingestion.pipeline import IngestionPipeline

    logger.info(
        "Starting document ingestion",
        document_id=document_id,
        mime_type=mime_type,
    )

    async with async_session_factory() as db:
        storage = await get_storage_provider()
        pipeline = IngestionPipeline(db, storage)
        try:
            stats = await pipeline.run(
                document_id=document_id,
                file_path=file_path,
                mime_type=mime_type,
                user_id=user_id,
            )
            logger.info(
                "Document ingestion completed",
                document_id=document_id,
                **stats,
            )
            return stats

        except Exception as e:
            logger.exception(
                "Document ingestion failed",
                document_id=document_id,
                error=str(e),
            )
            # Move to DLQ after max retries
            redis = ctx.get("redis")
            if redis:
                retry_key = f"rag:retry:{document_id}"
                retry_count = await redis.get(retry_key)
                retry_count = int(retry_count) if retry_count else 0

                if retry_count >= MAX_RETRIES:
                    await redis.lpush(
                        DLQ_KEY,
                        f"{document_id}:{file_path}:{mime_type}:{user_id}",
                    )
                    logger.warning(
                        "Document moved to dead-letter queue",
                        document_id=document_id,
                    )
                else:
                    await redis.incr(retry_key)
                    await redis.expire(retry_key, 86400)
                    logger.info(
                        "Document queued for retry",
                        document_id=document_id,
                        attempt=retry_count + 1,
                    )
            raise


async def cleanup_temp_files(ctx: dict[str, Any], file_path: str) -> bool:
    """Clean up temporary files via StorageProvider.

    Args:
        ctx: ARQ context.
        file_path: Storage path to clean up.

    Returns:
        True if cleanup was successful.
    """
    try:
        storage = await get_storage_provider()
        exists = await storage.exists(file_path)
        if exists:
            await storage.delete(file_path)
            logger.info("Cleaned up temp file", path=file_path)
        return True
    except Exception as e:
        logger.warning("Failed to clean up temp file", path=file_path, error=str(e))
        return False


async def retry_dead_letter(ctx: dict[str, Any]) -> int:
    """Re-process documents from the dead-letter queue.

    Returns:
        Number of documents re-queued.
    """
    redis = ctx.get("redis")
    if not redis:
        return 0

    count = 0
    while True:
        item = await redis.rpop(DLQ_KEY)
        if not item:
            break

        parts = item.decode().split(":")
        if len(parts) >= 4:
            document_id, file_path, mime_type, user_id = parts[0], parts[1], parts[2], parts[3]
            # Re-queue for processing

            await redis.lpush(
                "arq:queue",
                f"process_document({document_id}, {file_path}, {mime_type}, {user_id})",
            )
            count += 1

    if count:
        logger.info("Re-queued documents from dead-letter queue", count=count)
    return count


# ARQ Worker settings
class WorkerSettings:
    """Settings for the ARQ background worker."""

    functions = [process_document, cleanup_temp_files, retry_dead_letter]
    redis_settings = {
        "host": settings.REDIS_HOST,
        "port": settings.REDIS_PORT,
        "password": settings.REDIS_PASSWORD or None,
        "database": settings.REDIS_DB,
    }
    max_tries = MAX_RETRIES
    max_burst_jobs = 10
    job_timeout = 600  # 10 minutes max per job
    keep_result_seconds = 86400  # Keep results for 1 day
    keep_result_hours = 24
    poll_delay = 1.0  # Check for new jobs every second
