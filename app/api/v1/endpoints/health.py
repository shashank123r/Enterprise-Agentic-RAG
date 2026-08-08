"""Health check endpoints.

Provides liveness, readiness, and detailed component health probes.
"""

from fastapi import APIRouter, Request
from sqlalchemy import text

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.common import HealthCheckResponse, MessageResponse

router = APIRouter()
logger = get_logger(__name__)


@router.get(
    "/health/live",
    summary="Liveness probe",
    description="Returns 200 if the application is running.",
    response_model=MessageResponse,
)
async def liveness() -> MessageResponse:
    """Kubernetes liveness probe — confirms the process is alive."""
    return MessageResponse(message="alive", code="ok")


async def _check_database(request: Request) -> str:
    """Check PostgreSQL connectivity with short timeout.

    Uses a separate short-lived engine (NullPool, 3s timeout) so that
    the readiness check completes quickly even when the database is down.
    """
    try:
        from sqlalchemy import pool
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(
            settings.database_url,
            poolclass=pool.NullPool,
            connect_args={"timeout": 3, "command_timeout": 5},
        )
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        await engine.dispose()
        return "healthy"
    except Exception as e:
        logger.warning("Database health check failed (degraded)", exc_info=e)
        return "unhealthy"


async def _check_redis(request: Request) -> str:
    """Check Redis connectivity."""
    try:
        from app.cache.redis import redis_manager

        await redis_manager.client.ping()
        return "healthy"
    except Exception as e:
        logger.warning("Redis health check failed (non-fatal)", exc_info=e)
        return "unhealthy"


@router.get(
    "/health/ready",
    summary="Readiness probe",
    description="Returns 200 only when all critical dependencies are reachable.",
    response_model=HealthCheckResponse,
)
async def readiness(request: Request) -> HealthCheckResponse:
    """Kubernetes readiness probe — checks all critical dependencies."""
    db_status = await _check_database(request)
    cache_status = await _check_redis(request)

    checks = {
        "database": db_status,
        "cache": cache_status,
    }

    overall = "healthy" if all(v == "healthy" for v in checks.values()) else "degraded"

    return HealthCheckResponse(
        status=overall,
        version="0.1.0",
        environment=settings.ENVIRONMENT.value,
        checks=checks,
    )


@router.get(
    "/health",
    summary="Full health status",
    description="Detailed health information for all components.",
    response_model=HealthCheckResponse,
)
async def health(request: Request) -> HealthCheckResponse:
    """Full health check with all component statuses."""
    db_status = await _check_database(request)
    cache_status = await _check_redis(request)

    checks = {
        "database": db_status,
        "cache": cache_status,
    }

    overall = "healthy" if all(v == "healthy" for v in checks.values()) else "degraded"

    return HealthCheckResponse(
        status=overall,
        version="0.1.0",
        environment=settings.ENVIRONMENT.value,
        checks=checks,
    )
