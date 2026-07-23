"""Request/response logging middleware using structlog.

Provides structured logging of all HTTP requests with timing and metadata.
Propagates request_id to structlog context vars so downstream log entries
automatically include the correlation ID.
"""

import time
import uuid

import structlog
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.logging import get_logger

logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs all incoming requests with timing, status, and metadata."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Process and log the request."""
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        # Bind request_id to structlog context for traceability
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start_time = time.monotonic()

        response = await call_next(request)

        elapsed_ms = (time.monotonic() - start_time) * 1000

        logger.info(
            "Request completed",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            query_params=str(request.url.query),
            status_code=response.status_code,
            elapsed_ms=f"{elapsed_ms:.2f}",
            client_host=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent", "unknown"),
        )

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{elapsed_ms:.2f}ms"

        return response


def setup_request_logging(app: FastAPI) -> None:
    """Add request logging middleware to the application."""
    app.add_middleware(RequestLoggingMiddleware)
