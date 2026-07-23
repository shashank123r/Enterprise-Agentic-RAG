"""Rate limiting middleware using sliding window counter via Redis."""

import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.constants import REDIS_RATE_LIMIT_PREFIX
from app.core.logging import get_logger
from app.cache.redis import redis_manager

logger = get_logger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding window rate limiter using Redis.

    Tracks requests per client IP within a rolling window.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Check rate limit, process request, add rate limit headers."""
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        # Skip rate limiting for health endpoints
        if request.url.path.startswith("/api/v1/health"):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        now = int(time.time())
        window = 60  # 1-minute sliding window
        max_requests = settings.RATE_LIMIT_REQUESTS_PER_MINUTE

        key = f"{REDIS_RATE_LIMIT_PREFIX}{client_ip}:{now // window}"

        try:
            count = await redis_manager.incr(key)

            if count == 1:
                await redis_manager.expire(key, window + 1)

            response = await call_next(request)

            # Add rate limit headers
            remaining = max(0, max_requests - count)
            response.headers["X-RateLimit-Limit"] = str(max_requests)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Window"] = str(window)

            # If over limit, return 429
            if count > max_requests:
                from app.core.exceptions import RateLimitError

                raise RateLimitError(
                    message="Rate limit exceeded. Try again shortly.",
                    code="rate_limit_exceeded",
                )

            return response

        except Exception as e:
            if hasattr(e, "status_code") and getattr(e, "status_code") == 429:
                raise

            # If Redis is down, allow the request through (fail open)
            logger.warning("Rate limit check failed, allowing request", exc_info=e)
            return await call_next(request)

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        """Extract the real client IP from headers or connection."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        if request.client:
            return request.client.host or "unknown"
        return "unknown"


def setup_rate_limiting(app: FastAPI) -> None:
    """Add rate limiting middleware to the application."""
    app.add_middleware(RateLimitMiddleware)
