"""Embedding & Indexing exception hierarchy.

All exceptions extend AppException for consistent API error handling.
"""

from starlette.status import HTTP_404_NOT_FOUND, HTTP_500_INTERNAL_SERVER_ERROR, HTTP_503_SERVICE_UNAVAILABLE, HTTP_409_CONFLICT

from app.core.exceptions import AppException


class EmbeddingError(AppException):
    """Base exception for embedding operations."""

    def __init__(
        self,
        message: str = "Embedding error",
        code: str = "embedding_error",
        status_code: int = HTTP_500_INTERNAL_SERVER_ERROR,
        details: dict | None = None,
    ) -> None:
        super().__init__(message=message, code=code, status_code=status_code, details=details)


class EmbeddingServiceUnavailable(EmbeddingError):
    """Embedding provider (e.g. NVIDIA NIM) is unreachable."""

    def __init__(self, message: str = "Embedding service unavailable") -> None:
        super().__init__(message=message, code="embedding_service_unavailable", status_code=HTTP_503_SERVICE_UNAVAILABLE)


class EmbeddingAuthError(EmbeddingError):
    """Authentication with the embedding provider failed.

    This is a NON-RETRYABLE error. Providers must raise this instead of
    EmbeddingServiceUnavailable for 401/403 responses so the retry policy
    can correctly skip retrying on invalid credentials.
    """

    def __init__(self, message: str = "Embedding provider authentication failed") -> None:
        super().__init__(message=message, code="embedding_auth_error", status_code=HTTP_503_SERVICE_UNAVAILABLE)


class DuplicateInputIdError(EmbeddingError):
    """Duplicate input IDs detected in metadata before embedding.

    Raised before any API call is made — no provider requests are sent.
    """

    def __init__(self, duplicate_ids: list[str]) -> None:
        super().__init__(
            message=f"Duplicate input IDs detected: {duplicate_ids}",
            code="duplicate_input_ids",
            details={"duplicate_ids": duplicate_ids},
        )


class UnsupportedLanguageError(EmbeddingError):
    """One or more texts use a language not supported by the provider.

    Raised before any API call is made — no provider requests are sent.
    """

    def __init__(self, unsupported_languages: list[str], supported: list[str]) -> None:
        super().__init__(
            message=f"Unsupported language(s): {unsupported_languages}. Supported: {supported}",
            code="unsupported_language",
            details={"unsupported": unsupported_languages, "supported": supported},
        )


class EmbeddingTimeout(EmbeddingError):
    """Embedding request exceeded timeout."""

    def __init__(self, message: str = "Embedding request timed out") -> None:
        super().__init__(message=message, code="embedding_timeout", status_code=HTTP_503_SERVICE_UNAVAILABLE)


class IndexingError(AppException):
    """Base exception for indexing operations."""

    def __init__(
        self,
        message: str = "Indexing error",
        code: str = "indexing_error",
        status_code: int = HTTP_500_INTERNAL_SERVER_ERROR,
        details: dict | None = None,
    ) -> None:
        super().__init__(message=message, code=code, status_code=status_code, details=details)


class IndexingJobNotFound(IndexingError):
    """Requested indexing job does not exist."""

    def __init__(self, job_id: str) -> None:
        super().__init__(
            message=f"Indexing job not found: {job_id}",
            code="indexing_job_not_found",
            status_code=HTTP_404_NOT_FOUND,
        )


class CollectionNotFound(IndexingError):
    """Requested vector collection does not exist."""

    def __init__(self, collection_name: str) -> None:
        super().__init__(
            message=f"Collection not found: {collection_name}",
            code="collection_not_found",
            status_code=HTTP_404_NOT_FOUND,
        )


class CollectionError(IndexingError):
    """Collection operation failed."""

    def __init__(
        self,
        message: str = "Collection error",
        code: str = "collection_error",
        status_code: int = HTTP_500_INTERNAL_SERVER_ERROR,
    ) -> None:
        super().__init__(message=message, code=code, status_code=status_code)


class CacheError(AppException):
    """Embedding cache operation failed."""

    def __init__(
        self,
        message: str = "Cache error",
        code: str = "cache_error",
    ) -> None:
        super().__init__(message=message, code=code)
