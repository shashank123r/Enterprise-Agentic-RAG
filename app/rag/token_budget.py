"""Token budget manager — allocates context and response tokens within model limits.

Handles token counting, budget allocation, context truncation,
and adaptive budgeting for the RAG pipeline.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.rag.exceptions import RAGTokenBudgetExceeded

logger = get_logger(__name__)

# Rough estimate: 4 characters ≈ 1 token
_CHARS_PER_TOKEN = 4

# Default model context windows (updated as models change)
_MODEL_CONTEXT_LIMITS: dict[str, int] = {
    "nvidia/llama-3.1-nemotron-70b-instruct": 128000,
    "nvidia/llama-3.1-nemotron-8b-instruct": 128000,
    "meta/llama-3.1-70b-instruct": 128000,
    "meta/llama-3.1-8b-instruct": 128000,
    "mistralai/mixtral-8x22b-instruct": 65536,
    "gpt-4o": 128000,
    "gpt-4-turbo": 128000,
    "gpt-3.5-turbo": 16385,
    "claude-3-opus": 200000,
    "claude-3-sonnet": 200000,
    "default": 8192,
}


class TokenBudget:
    """Manages token budgets for RAG context and LLM responses.

    Allocates tokens between system prompt, context, conversation history,
    and response generation.

    Usage:
        budget = TokenBudget(model="nvidia/llama-3.1-nemotron-70b-instruct")
        context_budget = budget.allocate_for_context()
        response_budget = budget.allocate_for_response()
        total = budget.count_tokens("some text")
    """

    def __init__(
        self,
        model: str = "default",
        max_context_tokens: int | None = None,
        max_response_tokens: int | None = None,
        reserved_tokens: int = 2048,
    ) -> None:
        self._model = model
        self._reserved = reserved_tokens
        self._max_context = max_context_tokens
        self._max_response = max_response_tokens
        self._model_limit = _MODEL_CONTEXT_LIMITS.get(model)
        if self._model_limit is None:
            self._model_limit = _MODEL_CONTEXT_LIMITS["default"]
            logger.warning(
                "Unknown model context limit, using default",
                model=model,
                default_limit=self._model_limit,
            )

    @property
    def model_limit(self) -> int:
        """Get the model's maximum context window."""
        return self._model_limit

    @property
    def effective_limit(self) -> int:
        """Get the effective token limit after reserving overhead."""
        return self._model_limit - self._reserved

    def allocate_for_context(self) -> int:
        """Allocate tokens for the context window.

        Uses 60% of the effective limit by default, or the configured
        max_context_tokens if set.

        Returns:
            Available tokens for context.
        """
        if self._max_context is not None:
            return min(self._max_context, self.effective_limit)
        return int(self.effective_limit * 0.6)

    def allocate_for_response(self) -> int:
        """Allocate tokens for the response generation.

        Uses 25% of the effective limit by default, or the configured
        max_response_tokens if set.

        Returns:
            Available tokens for response.
        """
        if self._max_response is not None:
            return min(self._max_response, self.effective_limit)
        return int(self.effective_limit * 0.25)

    def allocate_for_system(self) -> int:
        """Allocate tokens for the system prompt.

        Returns:
            Fixed overhead of 1024 tokens for system instructions.
        """
        return 1024

    def count_tokens(self, text: str) -> int:
        """Estimate token count from text length.

        Uses 4 characters per token approximation.

        Args:
            text: Text to estimate.

        Returns:
            Approximate token count.
        """
        return max(1, len(text) // _CHARS_PER_TOKEN)

    def truncate_to_budget(self, text: str, budget: int) -> str:
        """Truncate text to fit within a token budget.

        Args:
            text: Text to potentially truncate.
            budget: Maximum token count.

        Returns:
            Truncated text if it exceeds budget, original if within budget.
        """
        current_tokens = self.count_tokens(text)
        if current_tokens <= budget:
            return text

        max_chars = budget * _CHARS_PER_TOKEN
        truncated = text[:max_chars]
        logger.warning(
            "Truncated text to fit budget",
            original_tokens=current_tokens,
            budget=budget,
        )
        return truncated + "\n[Content truncated due to token limit...]"

    def validate_budget(
        self,
        context_tokens: int,
        response_tokens: int,
        system_tokens: int,
    ) -> None:
        """Validate that the total token usage is within model limits.

        Args:
            context_tokens: Context token count.
            response_tokens: Response token count.
            system_tokens: System prompt token count.

        Raises:
            RAGTokenBudgetExceeded: If total exceeds model limit.
        """
        total = context_tokens + response_tokens + system_tokens
        if total > self._model_limit:
            raise RAGTokenBudgetExceeded(total_tokens=total, budget=self._model_limit)

    def get_usage_report(
        self,
        context_tokens: int,
        response_tokens: int,
        system_tokens: int,
    ) -> dict[str, Any]:
        """Get a detailed token usage report.

        Args:
            context_tokens: Context token count.
            response_tokens: Response token count.
            system_tokens: System prompt token count.

        Returns:
            Dict with usage details and percentages.
        """
        total = context_tokens + response_tokens + system_tokens
        return {
            "model": self._model,
            "model_limit": self._model_limit,
            "system_tokens": system_tokens,
            "context_tokens": context_tokens,
            "response_tokens": response_tokens,
            "total_tokens": total,
            "usage_percent": round((total / self._model_limit) * 100, 1) if self._model_limit else 0,
            "remaining_tokens": max(0, self._model_limit - total),
            "within_limit": total <= self._model_limit,
        }
