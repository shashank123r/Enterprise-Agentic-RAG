"""Tests for the rate limiting middleware.

Critical invariant: the 429 response MUST be returned without ever calling
call_next (the request should not be processed when over the limit).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.responses import Response
from starlette.testclient import TestClient as StarletteClient

from app.middleware.rate_limit import RateLimitMiddleware


def _make_app(*, rate_limit_enabled: bool = True, requests_per_minute: int = 5) -> FastAPI:
    app = FastAPI()

    @app.get("/test")
    async def endpoint():
        return {"ok": True}

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok"}

    return app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _run_dispatch(
    middleware: RateLimitMiddleware,
    path: str = "/test",
    client_ip: str = "1.2.3.4",
    redis_count: int = 1,
) -> Response:
    """Run dispatch() with a mocked Redis and a fake request."""
    mock_request = MagicMock(spec=Request)
    mock_request.url.path = path
    mock_request.headers.get = MagicMock(return_value=None)
    mock_request.client.host = client_ip

    async def call_next(req: Request) -> Response:
        return Response(content="ok", status_code=200)

    with patch("app.middleware.rate_limit.redis_manager") as mock_redis:
        mock_redis.incr = AsyncMock(return_value=redis_count)
        mock_redis.expire = AsyncMock()

        response = await middleware.dispatch(mock_request, call_next)

    return response


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRateLimitMiddleware:
    @pytest.fixture
    def middleware(self) -> RateLimitMiddleware:
        app = _make_app()
        return RateLimitMiddleware(app)

    @pytest.mark.asyncio
    async def test_under_limit_allows_request(self, middleware: RateLimitMiddleware):
        """Requests under the limit pass through and get rate limit headers."""
        with patch("app.middleware.rate_limit.settings") as mock_settings:
            mock_settings.RATE_LIMIT_ENABLED = True
            mock_settings.RATE_LIMIT_REQUESTS_PER_MINUTE = 60
            response = await _run_dispatch(middleware, redis_count=1)

        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers

    @pytest.mark.asyncio
    async def test_over_limit_returns_429_without_processing(self, middleware: RateLimitMiddleware):
        """CRITICAL: over-limit requests get 429 and call_next is never invoked."""
        call_next_called = False

        async def spy_call_next(req: Request) -> Response:
            nonlocal call_next_called
            call_next_called = True
            return Response(content="should not reach here", status_code=200)

        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/test"
        mock_request.headers.get = MagicMock(return_value=None)
        mock_request.client.host = "1.2.3.4"

        with (
            patch("app.middleware.rate_limit.settings") as mock_settings,
            patch("app.middleware.rate_limit.redis_manager") as mock_redis,
        ):
            mock_settings.RATE_LIMIT_ENABLED = True
            mock_settings.RATE_LIMIT_REQUESTS_PER_MINUTE = 5
            mock_redis.incr = AsyncMock(return_value=6)  # over the limit of 5
            mock_redis.expire = AsyncMock()

            response = await middleware.dispatch(mock_request, spy_call_next)

        assert response.status_code == 429
        assert not call_next_called, "call_next must NOT be called when rate limit exceeded"
        assert "Retry-After" in response.headers
        assert response.headers["X-RateLimit-Remaining"] == "0"

    @pytest.mark.asyncio
    async def test_health_endpoint_bypasses_rate_limit(self, middleware: RateLimitMiddleware):
        """Health endpoints are exempt from rate limiting."""
        with patch("app.middleware.rate_limit.settings") as mock_settings:
            mock_settings.RATE_LIMIT_ENABLED = True
            mock_settings.RATE_LIMIT_REQUESTS_PER_MINUTE = 5
            # Simulate a very high count — should still pass for health endpoint
            response = await _run_dispatch(middleware, path="/api/v1/health", redis_count=9999)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_rate_limit_disabled_allows_any_count(self, middleware: RateLimitMiddleware):
        """When RATE_LIMIT_ENABLED=False every request passes through."""
        with patch("app.middleware.rate_limit.settings") as mock_settings:
            mock_settings.RATE_LIMIT_ENABLED = False
            response = await _run_dispatch(middleware, redis_count=99999)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_redis_failure_fails_open(self, middleware: RateLimitMiddleware):
        """If Redis is unreachable, the request is allowed through (fail open)."""
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/test"
        mock_request.headers.get = MagicMock(return_value=None)
        mock_request.client.host = "1.2.3.4"

        async def call_next(_req: Request) -> Response:
            return Response(content="ok", status_code=200)

        with (
            patch("app.middleware.rate_limit.settings") as mock_settings,
            patch("app.middleware.rate_limit.redis_manager") as mock_redis,
        ):
            mock_settings.RATE_LIMIT_ENABLED = True
            mock_settings.RATE_LIMIT_REQUESTS_PER_MINUTE = 5
            mock_redis.incr = AsyncMock(side_effect=ConnectionError("Redis down"))

            response = await middleware.dispatch(mock_request, call_next)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_x_forwarded_for_used_as_client_ip(self, middleware: RateLimitMiddleware):
        """X-Forwarded-For header is respected for IP detection."""
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/test"
        mock_request.headers.get = MagicMock(
            side_effect=lambda h, d=None: "10.0.0.1, 10.0.0.2" if h == "X-Forwarded-For" else d
        )
        mock_request.client.host = "127.0.0.1"

        with (
            patch("app.middleware.rate_limit.settings") as mock_settings,
            patch("app.middleware.rate_limit.redis_manager") as mock_redis,
        ):
            mock_settings.RATE_LIMIT_ENABLED = True
            mock_settings.RATE_LIMIT_REQUESTS_PER_MINUTE = 60
            mock_redis.incr = AsyncMock(return_value=1)
            mock_redis.expire = AsyncMock()

            captured_key: list[str] = []

            original_incr = mock_redis.incr.side_effect

            async def capture_incr(key: str) -> int:
                captured_key.append(key)
                return 1

            mock_redis.incr = AsyncMock(side_effect=capture_incr)

            await middleware.dispatch(mock_request, lambda r: Response("ok", 200))

        assert any(
            "10.0.0.1" in k for k in captured_key
        ), "Rate limit key should use X-Forwarded-For IP"
