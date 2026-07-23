"""Retrieval exception hierarchy.

All exceptions extend AppException for consistent API error handling.
"""

from starlette.status import HTTP_404_NOT_FOUND, HTTP_400_BAD_REQUEST, HTTP_500_INTERNAL_SERVER_ERROR, HTTP_503_SERVICE_UNAVAILABLE

from app.core.exceptions import AppException


class RetrievalError(AppException):
    """Base exception for retrieval operations."""

    def __init__(
        self,
        message: str = "Retrieval error",
        code: str = "retrieval_error",
        status_code: int = HTTP_500_INTERNAL_SERVER_ERROR,
        details: dict | None = None,
    ) -> None:
        super().__init__(message=message, code=code, status_code=status_code, details=details)


class RetrieverNotFound(RetrievalError):
    """Requested retriever method is not supported."""

    def __init__(self, method: str) -> None:
        super().__init__(
            message=f"Retriever method not supported: {method}. Supported: dense, bm25, hybrid, parent_child",
            code="retriever_not_found",
            status_code=HTTP_404_NOT_FOUND,
        )


class RetrieverUnavailable(RetrievalError):
    """Retriever dependency (e.g. Milvus, BM25 index) is unavailable."""

    def __init__(self, message: str = "Retriever unavailable") -> None:
        super().__init__(message=message, code="retriever_unavailable", status_code=HTTP_503_SERVICE_UNAVAILABLE)


class RerankerError(RetrievalError):
    """Reranker operation failed."""

    def __init__(self, message: str = "Reranker error", code: str = "reranker_error") -> None:
        super().__init__(message=message, code=code, status_code=HTTP_500_INTERNAL_SERVER_ERROR)


class RerankerUnavailable(RetrievalError):
    """Reranker service is unavailable."""

    def __init__(self, message: str = "Reranker unavailable") -> None:
        super().__init__(message=message, code="reranker_unavailable", status_code=HTTP_503_SERVICE_UNAVAILABLE)


class QueryError(RetrievalError):
    """Query understanding operation failed."""

    def __init__(self, message: str = "Query processing error", code: str = "query_error") -> None:
        super().__init__(message=message, code=code, status_code=HTTP_400_BAD_REQUEST)


class ContextBuilderError(RetrievalError):
    """Context window construction failed."""

    def __init__(self, message: str = "Context builder error", code: str = "context_builder_error") -> None:
        super().__init__(message=message, code=code)


class BM25IndexError(RetrievalError):
    """BM25 index operation failed."""

    def __init__(self, message: str = "BM25 index error", code: str = "bm25_index_error") -> None:
        super().__init__(message=message, code=code)


class FilterError(RetrievalError):
    """Metadata filter parsing or execution failed."""

    def __init__(self, message: str = "Filter error", code: str = "filter_error") -> None:
        super().__init__(message=message, code=code, status_code=HTTP_400_BAD_REQUEST)
