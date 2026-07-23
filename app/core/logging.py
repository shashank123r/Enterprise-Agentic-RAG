"""Structured logging configuration using structlog.

Provides JSON-formatted logs for production and
colorized console output for development.
"""

import logging
import sys
from pathlib import Path
from typing import Any

import structlog
from structlog.processors import JSONRenderer

from app.core.config import Environment, LogFormat, settings


def setup_logging() -> None:
    """Configure structlog and standard logging for the application.

    Must be called once at application startup.
    """
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
    ]

    if settings.LOG_FORMAT == LogFormat.JSON:
        renderer: Any = JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(
            colors=settings.ENVIRONMENT == Environment.DEVELOPMENT,
            sort_keys=False,
        )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # Quiet noisy third-party loggers
    for logger_name in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    # File logging for audit trail
    if settings.ENVIRONMENT == Environment.PRODUCTION:
        log_path = Path(settings.LOG_FILE)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(log_path))
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    logger = get_logger(__name__)
    logger.info(
        "Logging configured",
        format=settings.LOG_FORMAT.value,
        level=settings.LOG_LEVEL,
        environment=settings.ENVIRONMENT.value,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance.

    Args:
        name: Logger name, typically __name__.

    Returns:
        A structlog-bound logger.
    """
    return structlog.get_logger(name or __name__)
