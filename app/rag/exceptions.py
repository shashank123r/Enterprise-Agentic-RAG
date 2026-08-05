"""RAG exception hierarchy."""

from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_500_INTERNAL_SERVER_ERROR,
    HTTP_503_SERVICE_UNAVAILABLE,
)

from app.core.exceptions import AppException


class RAGError(AppException):
    """Base exception for RAG operations."""

    def __init__(
        self,
        message: str = "RAG error",
        code: str = "rag_error",
        status_code: int = HTTP_500_INTERNAL_SERVER_ERROR,
        details: dict | None = None,
    ) -> None:
        super().__init__(message=message, code=code, status_code=status_code, details=details)


class RAGLLMUnavailable(RAGError):
    """LLM endpoint is unreachable."""

    def __init__(self, message: str = "LLM service unavailable") -> None:
        super().__init__(
            message=message, code="llm_unavailable", status_code=HTTP_503_SERVICE_UNAVAILABLE
        )


class RAGLLMError(RAGError):
    """LLM returned an error response."""

    def __init__(self, message: str = "LLM error") -> None:
        super().__init__(message=message, code="llm_error")


class RAGContextTooLarge(RAGError):
    """Context exceeds the model's token limit."""

    def __init__(self, context_tokens: int, max_tokens: int) -> None:
        super().__init__(
            message=f"Context too large: {context_tokens} tokens exceeds limit of {max_tokens}",
            code="context_too_large",
            details={"context_tokens": context_tokens, "max_tokens": max_tokens},
        )


class RAGGroundingError(RAGError):
    """Answer failed grounding validation."""

    def __init__(self, issues: list[str]) -> None:
        super().__init__(
            message=f"Answer failed grounding check with {len(issues)} issue(s)",
            code="grounding_error",
            status_code=HTTP_400_BAD_REQUEST,
            details={"issues": issues},
        )


class RAGCitationError(RAGError):
    """Citation could not be verified against source chunks."""

    def __init__(self, message: str = "Citation verification failed") -> None:
        super().__init__(message=message, code="citation_error")


class RAGTokenBudgetExceeded(RAGError):
    """Token budget exceeded for the RAG pipeline."""

    def __init__(self, total_tokens: int, budget: int) -> None:
        super().__init__(
            message=f"Token budget exceeded: {total_tokens} total > {budget} budget",
            code="token_budget_exceeded",
            details={"total_tokens": total_tokens, "budget": budget},
        )
