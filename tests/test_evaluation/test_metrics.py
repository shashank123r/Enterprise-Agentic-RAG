"""Tests for RAG evaluation metrics.

All tests are pure function tests — no I/O, no mocking needed.
Each test has a documented expected value so regressions are immediately visible.
"""

from __future__ import annotations

import pytest

from app.evaluation.metrics import (
    answer_relevancy_score,
    average_precision,
    context_precision,
    context_recall,
    faithfulness_score,
    mean_average_precision,
    mean_reciprocal_rank,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)


# ── recall_at_k ───────────────────────────────────────────────────────────

class TestRecallAtK:
    def test_perfect_recall(self):
        assert recall_at_k(["a", "b", "c"], ["a", "b", "c"], k=3) == 1.0

    def test_partial_recall(self):
        # 1 of 2 relevant in top-3 → 0.5
        assert recall_at_k(["a", "x", "y"], ["a", "b"], k=3) == pytest.approx(0.5)

    def test_zero_recall(self):
        assert recall_at_k(["x", "y", "z"], ["a", "b"], k=3) == 0.0

    def test_empty_relevant(self):
        assert recall_at_k(["a", "b"], [], k=2) == 0.0

    def test_k_less_than_total(self):
        # Only looking at top-2; relevant item "c" is at position 3 → not counted
        assert recall_at_k(["a", "x", "c"], ["a", "c"], k=2) == pytest.approx(0.5)

    def test_k_zero(self):
        assert recall_at_k(["a"], ["a"], k=0) == 0.0


# ── precision_at_k ────────────────────────────────────────────────────────

class TestPrecisionAtK:
    def test_perfect_precision(self):
        assert precision_at_k(["a", "b"], ["a", "b", "c"], k=2) == 1.0

    def test_partial_precision(self):
        # 1 of 3 retrieved is relevant → 1/3
        assert precision_at_k(["a", "x", "y"], ["a", "b"], k=3) == pytest.approx(1 / 3)

    def test_k_zero(self):
        assert precision_at_k(["a"], ["a"], k=0) == 0.0


# ── MRR ──────────────────────────────────────────────────────────────────

class TestMRR:
    def test_first_position(self):
        result = mean_reciprocal_rank([["a", "b", "c"]], [["a"]])
        assert result == pytest.approx(1.0)

    def test_second_position(self):
        result = mean_reciprocal_rank([["x", "a", "c"]], [["a"]])
        assert result == pytest.approx(0.5)

    def test_not_found(self):
        result = mean_reciprocal_rank([["x", "y", "z"]], [["a"]])
        assert result == 0.0

    def test_average_across_queries(self):
        # Q1: relevant at pos 1 (RR=1.0), Q2: relevant at pos 2 (RR=0.5)
        result = mean_reciprocal_rank(
            [["a", "b"], ["x", "a"]],
            [["a"], ["a"]],
        )
        assert result == pytest.approx(0.75)

    def test_empty_input(self):
        assert mean_reciprocal_rank([], []) == 0.0


# ── nDCG ─────────────────────────────────────────────────────────────────

class TestNDCG:
    def test_perfect_ranking(self):
        # Relevant items at top-2 positions → nDCG@2 = 1.0
        ndcg = ndcg_at_k(["a", "b", "x"], ["a", "b"], k=2)
        assert ndcg == pytest.approx(1.0)

    def test_reversed_ranking(self):
        # Relevant items at bottom of k
        ndcg_perfect = ndcg_at_k(["a", "b"], ["a", "b"], k=2)
        ndcg_reversed = ndcg_at_k(["b", "a"], ["a", "b"], k=2)
        # Both are perfect since both relevant items are within k
        assert ndcg_perfect == pytest.approx(1.0)
        assert ndcg_reversed == pytest.approx(1.0)

    def test_single_relevant_at_position_2(self):
        # DCG = 1/log2(3) ≈ 0.631, IDCG = 1/log2(2) = 1.0
        ndcg = ndcg_at_k(["x", "a", "y"], ["a"], k=3)
        import math
        expected = (1 / math.log2(3)) / (1 / math.log2(2))
        assert ndcg == pytest.approx(expected, abs=1e-3)

    def test_empty_relevant(self):
        assert ndcg_at_k(["a", "b"], [], k=3) == 0.0

    def test_k_zero(self):
        assert ndcg_at_k(["a"], ["a"], k=0) == 0.0


# ── Average Precision ─────────────────────────────────────────────────────

class TestAveragePrecision:
    def test_all_relevant_at_top(self):
        # Retrieved [a, b], both relevant → P@1=1.0, P@2=1.0 → AP=1.0
        ap = average_precision(["a", "b"], ["a", "b"])
        assert ap == pytest.approx(1.0)

    def test_relevant_at_second(self):
        # Retrieved [x, a], relevant=[a] → P@2=0.5 → AP=0.5
        ap = average_precision(["x", "a"], ["a"])
        assert ap == pytest.approx(0.5)

    def test_no_relevant_retrieved(self):
        assert average_precision(["x", "y"], ["a"]) == 0.0


# ── MAP ───────────────────────────────────────────────────────────────────

class TestMAP:
    def test_average_across_queries(self):
        # Q1: AP=1.0, Q2: AP=0.5 → MAP=0.75
        result = mean_average_precision(
            [["a", "b"], ["x", "a"]],
            [["a", "b"], ["a"]],
        )
        assert result == pytest.approx(0.75)


# ── Faithfulness ──────────────────────────────────────────────────────────

class TestFaithfulness:
    def test_fully_supported_answer(self):
        source = "The quarterly revenue grew by 23 percent due to cloud adoption"
        answer = "Revenue grew 23 percent due to cloud adoption"
        score = faithfulness_score(answer, [source])
        assert score > 0.5, f"Expected high faithfulness, got {score}"

    def test_unsupported_answer(self):
        source = "The company sells software products"
        answer = "The CEO resigned last year due to accounting irregularities"
        score = faithfulness_score(answer, [source])
        assert score < 0.3, f"Expected low faithfulness, got {score}"

    def test_empty_answer(self):
        assert faithfulness_score("", ["some source text"]) == 0.0

    def test_empty_sources(self):
        assert faithfulness_score("some answer", []) == 0.0


# ── Answer Relevancy ──────────────────────────────────────────────────────

class TestAnswerRelevancy:
    def test_relevant_answer(self):
        score = answer_relevancy_score(
            "The machine learning model achieves 95% accuracy on the test set",
            "What accuracy does the machine learning model achieve?",
        )
        assert score > 0.4

    def test_irrelevant_answer(self):
        score = answer_relevancy_score(
            "The weather in Paris is typically mild in spring",
            "What is the revenue forecast for Q4?",
        )
        assert score < 0.15

    def test_empty_question(self):
        assert answer_relevancy_score("some answer", "") == 0.0


# ── Context Precision ─────────────────────────────────────────────────────

class TestContextPrecision:
    def test_all_chunks_useful(self):
        chunk_texts = {
            "c1": "Revenue grew 23 percent in Q3 due to strong cloud sales",
            "c2": "Cloud adoption accelerated across enterprise segments",
        }
        answer = "Revenue grew 23 percent from cloud adoption and enterprise sales"
        score = context_precision(["c1", "c2"], answer, chunk_texts)
        assert score > 0.5

    def test_no_overlap(self):
        chunk_texts = {"c1": "The capital of France is Paris and the Eiffel Tower is famous"}
        answer = "Machine learning requires large training datasets and compute"
        score = context_precision(["c1"], answer, chunk_texts)
        assert score == 0.0

    def test_empty_retrieved(self):
        assert context_precision([], "some answer", {}) == 0.0


# ── Context Recall ────────────────────────────────────────────────────────

class TestContextRecall:
    def test_high_recall(self):
        chunk_texts = {"c1": "Machine learning models require training data and compute resources"}
        reference = "Training machine learning models requires compute and data"
        score = context_recall(["c1"], reference, chunk_texts)
        assert score > 0.4

    def test_low_recall(self):
        chunk_texts = {"c1": "The weather forecast shows rain next week in London"}
        reference = "Quantum computing uses qubits to process information exponentially faster"
        score = context_recall(["c1"], reference, chunk_texts)
        assert score < 0.1

    def test_empty_reference(self):
        assert context_recall(["c1"], "", {"c1": "text"}) == 0.0
