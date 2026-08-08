"""Vector store exception hierarchy.

All exceptions extend AppException for consistent API error handling.
"""

from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
    HTTP_500_INTERNAL_SERVER_ERROR,
    HTTP_503_SERVICE_UNAVAILABLE,
)

from app.core.exceptions import AppException


class VectorStoreError(AppException):
    """Base exception for vector store operations."""

    def __init__(
        self,
        message: str = "Vector store error",
        code: str = "vector_store_error",
        status_code: int = HTTP_500_INTERNAL_SERVER_ERROR,
        details: dict | None = None,
    ) -> None:
        super().__init__(message=message, code=code, status_code=status_code, details=details)


class VectorStoreUnavailable(VectorStoreError):
    """Vector database (e.g. Milvus) is unreachable."""

    def __init__(self, message: str = "Vector store is unavailable") -> None:
        super().__init__(
            message=message,
            code="vector_store_unavailable",
            status_code=HTTP_503_SERVICE_UNAVAILABLE,
        )


class VectorStoreAuthError(VectorStoreError):
    """Authentication with the vector database failed."""

    def __init__(self, message: str = "Vector store authentication failed") -> None:
        super().__init__(
            message=message,
            code="vector_store_auth_error",
            status_code=HTTP_503_SERVICE_UNAVAILABLE,
        )


class CollectionNotFound(VectorStoreError):
    """Requested collection does not exist."""

    def __init__(self, collection_name: str) -> None:
        super().__init__(
            message=f"Collection not found: {collection_name}",
            code="collection_not_found",
            status_code=HTTP_404_NOT_FOUND,
            details={"collection_name": collection_name},
        )


class CollectionAlreadyExists(VectorStoreError):
    """Attempted to create a collection that already exists."""

    def __init__(self, collection_name: str) -> None:
        super().__init__(
            message=f"Collection already exists: {collection_name}",
            code="collection_already_exists",
            status_code=HTTP_409_CONFLICT,
            details={"collection_name": collection_name},
        )


class CollectionNotReady(VectorStoreError):
    """Collection exists but is not yet ready for queries."""

    def __init__(self, collection_name: str) -> None:
        super().__init__(
            message=f"Collection not ready: {collection_name}",
            code="collection_not_ready",
            status_code=HTTP_503_SERVICE_UNAVAILABLE,
            details={"collection_name": collection_name},
        )


class VectorDimensionMismatch(VectorStoreError):
    """Vector dimension does not match collection schema."""

    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(
            message=f"Vector dimension mismatch: expected {expected}, got {actual}",
            code="vector_dimension_mismatch",
            status_code=HTTP_400_BAD_REQUEST,
            details={"expected": expected, "actual": actual},
        )


class BatchInsertError(VectorStoreError):
    """Batch insert operation failed partially or fully."""

    def __init__(
        self,
        message: str = "Batch insert failed",
        attempted: int = 0,
        succeeded: int = 0,
        errors: list[str] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="batch_insert_error",
            details={
                "attempted": attempted,
                "succeeded": succeeded,
                "errors": errors or [],
            },
        )


class VectorStoreTimeout(VectorStoreError):
    """Vector store operation exceeded timeout."""

    def __init__(self, message: str = "Vector store operation timed out") -> None:
        super().__init__(
            message=message, code="vector_store_timeout", status_code=HTTP_503_SERVICE_UNAVAILABLE
        )


class IndexError_(VectorStoreError):
    """Vector index operation failed."""

    def __init__(self, message: str = "Index operation failed") -> None:
        super().__init__(message=message, code="index_error")
