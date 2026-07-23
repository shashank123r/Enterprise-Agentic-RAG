"""Centralized exception hierarchy and FastAPI exception handlers.

All custom exceptions inherit from AppException for consistent handling.
"""

from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_401_UNAUTHORIZED,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
    HTTP_422_UNPROCESSABLE_CONTENT,
    HTTP_429_TOO_MANY_REQUESTS,
    HTTP_500_INTERNAL_SERVER_ERROR,
)

from app.core.logging import get_logger

logger = get_logger(__name__)


class AppException(Exception):
    """Base application exception with structured context."""

    def __init__(
        self,
        message: str = "An application error occurred",
        code: str = "internal_error",
        status_code: int = HTTP_500_INTERNAL_SERVER_ERROR,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class NotFoundError(AppException):
    """Resource not found."""

    def __init__(
        self,
        message: str = "Resource not found",
        code: str = "not_found",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=HTTP_404_NOT_FOUND,
            details=details,
        )


class AuthenticationError(AppException):
    """Authentication failed."""

    def __init__(
        self,
        message: str = "Authentication failed",
        code: str = "authentication_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=HTTP_401_UNAUTHORIZED,
            details=details,
        )


class AuthorizationError(AppException):
    """Insufficient permissions."""

    def __init__(
        self,
        message: str = "Insufficient permissions",
        code: str = "authorization_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=HTTP_403_FORBIDDEN,
            details=details,
        )


class ValidationError(AppException):
    """Request validation failed."""

    def __init__(
        self,
        message: str = "Validation failed",
        code: str = "validation_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=HTTP_422_UNPROCESSABLE_CONTENT,
            details=details,
        )


class ConflictError(AppException):
    """Resource conflict (e.g., duplicate)."""

    def __init__(
        self,
        message: str = "Resource conflict",
        code: str = "conflict",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=HTTP_409_CONFLICT,
            details=details,
        )


class RateLimitError(AppException):
    """Rate limit exceeded."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        code: str = "rate_limit_exceeded",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=HTTP_429_TOO_MANY_REQUESTS,
            details=details,
        )


class ServiceUnavailableError(AppException):
    """External service unavailable."""

    def __init__(
        self,
        message: str = "Service unavailable",
        code: str = "service_unavailable",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=HTTP_503_SERVICE_UNAVAILABLE,
            details=details,
        )


def error_response(
    status_code: int,
    message: str,
    code: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    """Build a standardized error JSON response."""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            }
        },
    )


async def app_exception_handler(
    _request: Request,
    exc: AppException,
) -> JSONResponse:
    """Handle AppException and subclasses."""
    logger.error(
        "Application error",
        extra={
            "code": exc.code,
            "message": exc.message,
            "status_code": exc.status_code,
            "details": exc.details,
        },
    )
    return error_response(
        status_code=exc.status_code,
        message=exc.message,
        code=exc.code,
        details=exc.details,
    )


def _sanitize(obj: Any) -> Any:
    """Recursively convert non-serializable objects (e.g. bytes) to strings."""
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(item) for item in obj]
    if isinstance(obj, tuple):
        return tuple(_sanitize(item) for item in obj)
    return obj


async def validation_exception_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Handle Pydantic/FastAPI validation errors, safely handling non-serializable types."""
    errors = _sanitize(exc.errors())
    logger.warning("Validation error", extra={"errors": errors})
    return error_response(
        status_code=HTTP_422_UNPROCESSABLE_CONTENT,
        message="Request validation failed",
        code="validation_error",
        details={"errors": errors},
    )


async def http_exception_handler(
    _request: Request,
    exc: HTTPException,
) -> JSONResponse:
    """Handle standard HTTPException."""
    logger.warning(
        "HTTP exception",
        extra={"status_code": exc.status_code, "detail": exc.detail},
    )
    return error_response(
        status_code=exc.status_code,
        message=str(exc.detail),
        code="http_error",
    )


async def unhandled_exception_handler(
    _request: Request,
    exc: Exception,
) -> JSONResponse:
    """Catch-all for unhandled exceptions (500)."""
    logger.exception("Unhandled exception", exc_info=exc)
    return error_response(
        status_code=HTTP_500_INTERNAL_SERVER_ERROR,
        message="An unexpected error occurred",
        code="internal_error",
    )
