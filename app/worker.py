"""ARQ background worker entry point for document ingestion.

Run with::

    arq app.worker.WorkerSettings

Or via Docker::

    docker compose run --rm worker
"""

from app.core.config import settings
from app.core.logging import get_logger, setup_logging

logger = get_logger(__name__)


async def _worker_startup(ctx: dict) -> None:
    """Initialize logging and resources when the worker starts."""
    setup_logging()
    logger.info(
        "ARQ worker started",
        redis_host=settings.REDIS_HOST,
        redis_port=settings.REDIS_PORT,
    )


async def _worker_shutdown(ctx: dict) -> None:
    """Clean up when the worker stops."""
    logger.info("ARQ worker shutting down")


class WorkerSettings:
    """ARQ worker configuration for document ingestion.

    Usage::

        arq app.worker.WorkerSettings
    """

    from app.ingestion.tasks import (  # type: ignore[misc]
        cleanup_temp_files,
        process_document,
        retry_dead_letter,
    )

    functions = [process_document, cleanup_temp_files, retry_dead_letter]
    redis_settings = {
        "host": settings.REDIS_HOST,
        "port": settings.REDIS_PORT,
        "password": settings.REDIS_PASSWORD or None,
        "database": settings.REDIS_DB,
    }
    max_tries = 3
    max_burst_jobs = 10
    job_timeout = 600  # 10 minutes
    keep_result_seconds = 86400
    keep_result_hours = 24
    poll_delay = 1.0
    on_startup = _worker_startup
    on_shutdown = _worker_shutdown
