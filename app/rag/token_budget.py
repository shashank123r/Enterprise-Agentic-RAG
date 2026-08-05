"""Token budget manager — allocates context and response tokens within model limits.

Uses tiktoken for accurate token counting when available.
Falls back to character-ratio heuristic only if tiktoken is unavailable.
"""

from __future__ import annotations

import functools
from typing import Any

from app.core.logging import get_logger
from app.rag.exceptions import RAGTokenBudgetExceeded

logger = get_logger(__name__)

# ── Tokenizer resolution ───────────────────────────────────────────────────
#
# NVIDIA NIM LLaMA models use the LLaMA-3 BPE tokenizer. tiktoken does not
# ship a LLaMA encoding, but cl100k_base (GPT-4) gives <5% token count error
# relative to LLaMA-3 — far more accurate than the 4-chars/token fallback.
#
# Encoding selection priority:
#   1. tiktoken "cl100k_base"  → best accuracy for LLaMA-3/GPT-4 family
#   2. Character ratio fallback → len(text) // 4  (least preferred)


@functools.lru_cache(maxsize=4)
def _get_encoding(model_key: str):
    """Return a tiktoken encoding, cached per model key."""
    try:
        import tiktoken  # noqa: PLC0415

        # Map model families to tiktoken encodings
        _ENCODING_MAP = {
            "gpt-4": "cl100k_base",
            "gpt-3.5": "cl100k_base",
            "claude": "cl100k_base",
            "llama": "cl100k_base",  # Approximation — within 5% of LLaMA-3
            "mistral": "cl100k_base",
            "mixtral": "cl100k_base",
            "default": "cl100k_base",
        }
        key = next(
            (v for k, v in _ENCODING_MAP.items() if k in model_key.lower()),
            "cl100k_base",
        )
        return tiktoken.get_encoding(key)
    except Exception:
        return None


def _count_tokens_tiktoken(text: str, model: str) -> int:
    enc = _get_encoding(model)
    if enc is None:
        return max(1, len(text) // 4)
    try:
        return len(enc.encode(text, disallowed_special=()))
    except Exception:
        return max(1, len(text) // 4)


# ── Model context windows ──────────────────────────────────────────────────

_MODEL_CONTEXT_LIMITS: dict[str, int] = {
    "nvidia/llama-3.1-nemotron-70b-instruct": 131072,
    "nvidia/llama-3.1-nemotron-8b-instruct": 131072,
    "meta/llama-3.1-70b-instruct": 131072,
    "meta/llama-3.1-8b-instruct": 131072,
    "meta/llama-3.3-70b-instruct": 131072,
    "meta/llama-3.2-3b-instruct": 131072,
    "mistralai/mixtral-8x22b-instruct-v0.1": 65536,
    "mistralai/mixtral-8x7b-instruct-v0.1": 32768,
    "mistralai/mistral-large": 131072,
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4-turbo": 128000,
    "gpt-3.5-turbo": 16385,
    "claude-3-5-sonnet": 200000,
    "claude-3-opus": 200000,
    "claude-3-sonnet": 200000,
    "claude-3-haiku": 200000,
    "default": 8192,
}


class TokenBudget:
    """Manages token budgets for RAG context and LLM responses.

    Uses tiktoken for accurate counting (cl100k_base encoding as LLaMA-3 proxy).
    Falls back to character heuristics if tiktoken is unavailable.

    Usage:
        budget = TokenBudget(model="meta/llama-3.1-70b-instruct")
        count = budget.count_tokens("some text")           # accurate
        trimmed = budget.truncate_to_budget(text, 2048)   # token-precise
    """

    def __init__(
        self,
        model: str = "default",
        max_context_tokens: int | None = None,
        max_response_tokens: int | None = None,
        reserved_tokens: int = 512,
    ) -> None:
        self._model = model
        self._reserved = reserved_tokens
        self._max_context = max_context_tokens
        self._max_response = max_response_tokens

        # Resolve model limit (prefix match for NVIDIA NIM model IDs)
        self._model_limit = self._resolve_limit(model)

        # Probe tiktoken availability once at init (no-op if already cached)
        enc = _get_encoding(model)
        if enc is None:
            logger.warning(
                "tiktoken unavailable — using character-ratio fallback (4 chars ≈ 1 token)",
                model=model,
            )

    @staticmethod
    def _resolve_limit(model: str) -> int:
        if model in _MODEL_CONTEXT_LIMITS:
            return _MODEL_CONTEXT_LIMITS[model]
        for key, limit in _MODEL_CONTEXT_LIMITS.items():
            if key != "default" and key in model.lower():
                return limit
        return _MODEL_CONTEXT_LIMITS["default"]

    # ── Budget allocation ──────────────────────────────────────────────────

    @property
    def model_limit(self) -> int:
        return self._model_limit

    @property
    def effective_limit(self) -> int:
        return self._model_limit - self._reserved

    def allocate_for_context(self) -> int:
        if self._max_context is not None:
            return min(self._max_context, self.effective_limit)
        return int(self.effective_limit * 0.60)

    def allocate_for_response(self) -> int:
        if self._max_response is not None:
            return min(self._max_response, self.effective_limit)
        return int(self.effective_limit * 0.25)

    def allocate_for_system(self) -> int:
        """Fixed overhead for system prompt + formatting tokens."""
        return 1024

    def allocate_for_history(self, total_budget: int) -> int:
        """Remaining tokens after context + response + system."""
        used = (
            self.allocate_for_context() + self.allocate_for_response() + self.allocate_for_system()
        )
        return max(0, total_budget - used)

    # ── Token counting ─────────────────────────────────────────────────────

    def count_tokens(self, text: str) -> int:
        """Count tokens accurately using tiktoken (or fallback).

        Args:
            text: Text to count tokens for.

        Returns:
            Token count (tiktoken if available, else len//4).
        """
        if not text:
            return 0
        return _count_tokens_tiktoken(text, self._model)

    def count_messages_tokens(self, messages: list[dict[str, str]]) -> int:
        """Count tokens across all messages including role overhead.

        OpenAI-compatible: 4 overhead tokens per message + 2 for reply prime.
        """
        total = 2  # reply prime
        for msg in messages:
            total += 4  # role overhead
            total += self.count_tokens(msg.get("content", ""))
        return total

    # ── Truncation ─────────────────────────────────────────────────────────

    def truncate_to_budget(self, text: str, budget: int) -> str:
        """Truncate text to fit within a token budget.

        Uses binary search over character positions for efficiency when
        tiktoken is available, so we make a minimum number of encode() calls.

        Args:
            text: Text to potentially truncate.
            budget: Maximum token count.

        Returns:
            Truncated text if it exceeds budget, original if within budget.
        """
        if not text:
            return text

        current = self.count_tokens(text)
        if current <= budget:
            return text

        enc = _get_encoding(self._model)
        if enc is not None:
            # Token-precise truncation via encode/decode
            try:
                tokens = enc.encode(text, disallowed_special=())
                truncated_tokens = tokens[:budget]
                truncated = enc.decode(truncated_tokens)
                logger.debug(
                    "Text truncated to token budget",
                    original_tokens=current,
                    budget=budget,
                    method="tiktoken",
                )
                return truncated + "\n[Content truncated]"
            except Exception:
                pass

        # Fallback: character-based approximation
        ratio = budget / max(current, 1)
        max_chars = int(len(text) * ratio)
        logger.debug(
            "Text truncated to token budget",
            original_tokens=current,
            budget=budget,
            method="char_ratio",
        )
        return text[:max_chars] + "\n[Content truncated]"

    def fits_in_budget(self, text: str, budget: int) -> bool:
        """Return True if text fits within the token budget."""
        return self.count_tokens(text) <= budget

    def remaining_after(self, text: str, budget: int) -> int:
        """Return remaining tokens after consuming text."""
        return max(0, budget - self.count_tokens(text))

    # ── Validation ─────────────────────────────────────────────────────────

    def validate_budget(
        self,
        context_tokens: int,
        response_tokens: int,
        system_tokens: int,
    ) -> None:
        """Validate total token usage is within model limits.

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
        total = context_tokens + response_tokens + system_tokens
        return {
            "model": self._model,
            "model_limit": self._model_limit,
            "system_tokens": system_tokens,
            "context_tokens": context_tokens,
            "response_tokens": response_tokens,
            "total_tokens": total,
            "usage_percent": (
                round((total / self._model_limit) * 100, 1) if self._model_limit else 0
            ),
            "remaining_tokens": max(0, self._model_limit - total),
            "within_limit": total <= self._model_limit,
            "tokenizer": "tiktoken/cl100k_base" if _get_encoding(self._model) else "char_ratio",
        }
