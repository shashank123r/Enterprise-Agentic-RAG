"""Tests for the improved TokenBudget with tiktoken support."""

from __future__ import annotations

import pytest

from app.rag.token_budget import _MODEL_CONTEXT_LIMITS, TokenBudget


class TestTokenBudget:
    def test_known_model_limit(self):
        budget = TokenBudget(model="meta/llama-3.1-70b-instruct")
        assert budget.model_limit == 131072

    def test_default_model_limit(self):
        budget = TokenBudget(model="unknown-model-xyz")
        assert budget.model_limit == _MODEL_CONTEXT_LIMITS["default"]

    def test_prefix_match_model(self):
        # "gpt-4o-mini" should match "gpt-4o" prefix
        budget = TokenBudget(model="gpt-4o-mini")
        assert budget.model_limit > 0

    def test_count_tokens_non_zero(self):
        budget = TokenBudget()
        count = budget.count_tokens("Hello, world!")
        assert count >= 1

    def test_count_tokens_empty(self):
        budget = TokenBudget()
        assert budget.count_tokens("") == 0

    def test_count_tokens_proportional(self):
        budget = TokenBudget()
        short = budget.count_tokens("Hello")
        long = budget.count_tokens("Hello world this is a longer sentence with more tokens")
        assert long > short

    def test_truncate_to_budget(self):
        budget = TokenBudget()
        text = "word " * 1000  # Very long text
        truncated = budget.truncate_to_budget(text, budget=50)
        # Truncated text should be significantly shorter
        assert len(truncated) < len(text)
        assert budget.count_tokens(truncated) <= 55  # Slight slack for suffix

    def test_truncate_within_budget_unchanged(self):
        budget = TokenBudget()
        text = "Short text."
        result = budget.truncate_to_budget(text, budget=1000)
        assert result == text

    def test_fits_in_budget(self):
        budget = TokenBudget()
        assert budget.fits_in_budget("short", 100)
        assert not budget.fits_in_budget("word " * 10000, 10)

    def test_allocate_for_context(self):
        budget = TokenBudget(model="default", max_context_tokens=2000)
        alloc = budget.allocate_for_context()
        assert alloc <= 2000

    def test_allocate_for_response(self):
        budget = TokenBudget(model="default", max_response_tokens=512)
        alloc = budget.allocate_for_response()
        assert alloc <= 512

    def test_validate_budget_raises_on_overflow(self):
        from app.rag.exceptions import RAGTokenBudgetExceeded

        budget = TokenBudget(model="default")  # limit = 8192
        with pytest.raises(RAGTokenBudgetExceeded):
            budget.validate_budget(
                context_tokens=10000,
                response_tokens=1000,
                system_tokens=500,
            )

    def test_get_usage_report_structure(self):
        budget = TokenBudget()
        report = budget.get_usage_report(1000, 500, 200)
        assert "tokenizer" in report
        assert "usage_percent" in report
        assert report["within_limit"] is True

    def test_count_messages_tokens(self):
        budget = TokenBudget()
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "What is the capital of France?"},
        ]
        total = budget.count_messages_tokens(messages)
        assert total >= 10  # Must be non-trivial

    def test_remaining_after(self):
        budget = TokenBudget()
        remaining = budget.remaining_after("hello world", budget=100)
        assert 0 < remaining < 100
