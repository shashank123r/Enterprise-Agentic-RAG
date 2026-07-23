"""Tests for health check endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_liveness(client: AsyncClient) -> None:
    """Test the liveness probe returns 200."""
    response = await client.get("/api/v1/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "alive"
    assert data["code"] == "ok"


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient) -> None:
    """Test the full health check endpoint."""
    response = await client.get("/api/v1/health")
    assert response.status_code in (200, 503)
    data = response.json()
    assert "status" in data
    assert "version" in data
    assert "environment" in data
    assert "checks" in data


@pytest.mark.asyncio
async def test_readiness(client: AsyncClient) -> None:
    """Test the readiness probe."""
    response = await client.get("/api/v1/health/ready")
    assert response.status_code in (200, 503)
    data = response.json()
    assert data["status"] in ("healthy", "degraded")
    assert "database" in data["checks"]
