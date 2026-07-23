"""Common Pydantic V2 schemas — pagination, health, generic responses."""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE

T = TypeVar("T")


class PaginationParams(BaseModel):
    """Query parameters for paginated endpoints."""

    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    size: int = Field(
        default=DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        description="Items per page",
    )


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper."""

    items: list[T]
    total: int
    page: int
    size: int
    pages: int

    @classmethod
    def create(
        cls,
        items: list[T],
        total: int,
        page: int,
        size: int,
    ) -> "PaginatedResponse[T]":
        """Create a paginated response with computed page count."""
        return cls(
            items=items,
            total=total,
            page=page,
            size=size,
            pages=max(1, (total + size - 1) // size),
        )


class MessageResponse(BaseModel):
    """Simple message response."""

    message: str = Field(..., description="Response message")
    code: str = Field("success", description="Response code")


class HealthCheckResponse(BaseModel):
    """Health check endpoint response."""

    status: str = Field("healthy", description="Overall health status")
    version: str = Field("0.1.0", description="Application version")
    environment: str = Field("development", description="Deployment environment")
    checks: dict[str, str] = Field(
        default_factory=dict,
        description="Individual component health statuses",
    )


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: dict[str, Any] = Field(
        ...,
        description="Error details with code, message, and optional details",
    )
