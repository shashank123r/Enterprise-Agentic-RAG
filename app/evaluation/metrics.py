"""RAG evaluation metrics.

Implements industry-standard retrieval and generation metrics:

Retrieval:
  - Recall@K          — fraction of relevant items in top-K results
  - Precision@K       — fraction of top-K results that are relevant
  - MRR               — Mean Reciprocal Rank (first relevant position)
  - nDCG@K            — Normalized Discounted Cumulative Gain
  - Average Precision — area under precision-recall curve
  - MAP               — Mean Average Precision across queries

Generation / RAG quality:
  - faithfulness_score       — lexical overlap between answer and sources
  - answer_relevancy_score   — answer covers the question's key terms
  - context_precision        — retrieved chunks actually useful for answer
  - context_recall           — necessary information present in retrieved chunks

All functions are pure (no I/O, no side effects) and accept plain Python
types — no ORM or schema objects required. This makes them trivially testable.
"""

from __future__ import annotations

import math
import re
from typing import Sequence

# ── Retrieval Metrics ──────────────────────────────────────────────────────


def recall_at_k(
    retrieved: Sequence[str],
    relevant: Sequence[str],
    k: int,
) -> float:
    """Recall@K: fraction of relevant items found in top-K retrieved results.

    Args:
        retrieved: Ordered list of retrieved item IDs (ranked 1st to last).
        relevant: Set of ground truth relevant item IDs.
        k: Cutoff rank.

    Returns:
        Recall@K in [0, 1]. Returns 0 if relevant is empty.
    """
    if not relevant:
        return 0.0
    top_k = set(retrieved[:k])
    relevant_set = set(relevant)
    return len(top_k & relevant_set) / len(relevant_set)


def precision_at_k(
    retrieved: Sequence[str],
    relevant: Sequence[str],
    k: int,
) -> float:
    """Precision@K: fraction of top-K retrieved items that are relevant.

    Args:
        retrieved: Ordered list of retrieved item IDs.
        relevant: Ground truth relevant item IDs.
        k: Cutoff rank.

    Returns:
        Precision@K in [0, 1]. Returns 0 if k == 0.
    """
    if k == 0:
        return 0.0
    top_k = retrieved[:k]
    relevant_set = set(relevant)
    return sum(1 for r in top_k if r in relevant_set) / k


def mean_reciprocal_rank(
    retrieved_lists: Sequence[Sequence[str]],
    relevant_lists: Sequence[Sequence[str]],
) -> float:
    """MRR: average of reciprocal ranks of the first relevant result.

    Args:
        retrieved_lists: List of ranked result lists, one per query.
        relevant_lists: List of ground truth relevant sets, one per query.

    Returns:
        MRR in [0, 1].
    """
    rr_sum = 0.0
    n = len(retrieved_lists)
    if n == 0:
        return 0.0
    for retrieved, relevant in zip(retrieved_lists, relevant_lists):
        relevant_set = set(relevant)
        for rank, item_id in enumerate(retrieved, 1):
            if item_id in relevant_set:
                rr_sum += 1.0 / rank
                break
    return rr_sum / n


def ndcg_at_k(
    retrieved: Sequence[str],
    relevant: Sequence[str],
    k: int,
    graded_relevance: dict[str, float] | None = None,
) -> float:
    """nDCG@K: Normalized Discounted Cumulative Gain.

    Supports both binary relevance (default) and graded relevance.

    Args:
        retrieved: Ordered list of retrieved item IDs.
        relevant: Ground truth relevant item IDs.
        k: Cutoff rank.
        graded_relevance: Optional dict mapping item_id → relevance grade.
            If None, binary relevance is used (1 if in relevant, 0 otherwise).

    Returns:
        nDCG@K in [0, 1].
    """
    if k == 0 or not relevant:
        return 0.0

    relevant_set = set(relevant)

    def rel(item_id: str) -> float:
        if graded_relevance:
            return graded_relevance.get(item_id, 0.0)
        return 1.0 if item_id in relevant_set else 0.0

    # DCG
    dcg = sum(rel(item) / math.log2(rank + 1) for rank, item in enumerate(retrieved[:k], 1))

    # IDCG — ideal ranking
    ideal_grades = sorted(
        [rel(item) for item in relevant],
        reverse=True,
    )[:k]
    idcg = sum(grade / math.log2(rank + 1) for rank, grade in enumerate(ideal_grades, 1))

    return dcg / idcg if idcg > 0 else 0.0


def average_precision(
    retrieved: Sequence[str],
    relevant: Sequence[str],
) -> float:
    """Average Precision (AP) for a single query.

    Area under the precision-recall curve.

    Args:
        retrieved: Ordered list of retrieved item IDs.
        relevant: Ground truth relevant item IDs.

    Returns:
        AP in [0, 1].
    """
    if not relevant:
        return 0.0
    relevant_set = set(relevant)
    hits = 0
    ap = 0.0
    for rank, item in enumerate(retrieved, 1):
        if item in relevant_set:
            hits += 1
            ap += hits / rank
    return ap / len(relevant_set) if relevant_set else 0.0


def mean_average_precision(
    retrieved_lists: Sequence[Sequence[str]],
    relevant_lists: Sequence[Sequence[str]],
) -> float:
    """MAP: Mean Average Precision across multiple queries."""
    if not retrieved_lists:
        return 0.0
    return sum(average_precision(r, rel) for r, rel in zip(retrieved_lists, relevant_lists)) / len(
        retrieved_lists
    )


# ── Generation / RAG Quality Metrics ──────────────────────────────────────


def _tokenize(text: str) -> set[str]:
    """Simple whitespace+punctuation tokenizer for overlap computation."""
    tokens = re.findall(r"\b[a-z0-9][a-z0-9\-']*\b", text.lower())
    stopwords = frozenset(
        "a an the and or but in on at to for of with by from that this "
        "is are was were be been have has had do does did will would "
        "could should may might can what when where who why how which".split()
    )
    return {t for t in tokens if t not in stopwords and len(t) >= 3}


def faithfulness_score(
    answer: str,
    source_texts: Sequence[str],
) -> float:
    """Faithfulness: token-level F1 overlap between answer and sources.

    Measures how much of the answer is supported by the retrieved sources.
    High faithfulness → answer is grounded; low → potential hallucination.

    Args:
        answer: Generated answer text.
        source_texts: List of retrieved chunk texts.

    Returns:
        Faithfulness score in [0, 1].
    """
    if not answer.strip() or not source_texts:
        return 0.0

    answer_tokens = _tokenize(answer)
    source_tokens = _tokenize(" ".join(source_texts))

    if not answer_tokens:
        return 0.0

    overlap = answer_tokens & source_tokens
    return len(overlap) / len(answer_tokens)


def answer_relevancy_score(
    answer: str,
    question: str,
) -> float:
    """Answer Relevancy: how many question key terms appear in the answer.

    A high score indicates the answer addresses the question directly.
    A low score may indicate off-topic or evasive answers.

    Args:
        answer: Generated answer text.
        question: Original question.

    Returns:
        Relevancy score in [0, 1].
    """
    if not question.strip() or not answer.strip():
        return 0.0

    question_tokens = _tokenize(question)
    answer_tokens = _tokenize(answer)

    if not question_tokens:
        return 0.0

    coverage = question_tokens & answer_tokens
    return len(coverage) / len(question_tokens)


def context_precision(
    retrieved_chunk_ids: Sequence[str],
    answer: str,
    chunk_texts: dict[str, str],
) -> float:
    """Context Precision: fraction of retrieved chunks actually used in answer.

    Estimates which retrieved chunks contributed to the answer by checking
    token overlap between each chunk and the generated answer.

    Args:
        retrieved_chunk_ids: IDs of retrieved chunks (in rank order).
        answer: Generated answer text.
        chunk_texts: Map of chunk_id → chunk text.

    Returns:
        Context precision in [0, 1].
    """
    if not retrieved_chunk_ids or not answer:
        return 0.0

    answer_tokens = _tokenize(answer)
    if not answer_tokens:
        return 0.0

    useful = 0
    for cid in retrieved_chunk_ids:
        text = chunk_texts.get(cid, "")
        chunk_tokens = _tokenize(text)
        # A chunk is "useful" if it shares non-trivial overlap with the answer
        overlap_ratio = len(chunk_tokens & answer_tokens) / max(len(chunk_tokens), 1)
        if overlap_ratio >= 0.05:  # At least 5% token overlap
            useful += 1

    return useful / len(retrieved_chunk_ids)


def context_recall(
    retrieved_chunk_ids: Sequence[str],
    reference_answer: str,
    chunk_texts: dict[str, str],
) -> float:
    """Context Recall: fraction of reference answer tokens covered by retrieved chunks.

    Measures whether the retrieved chunks collectively contain the information
    needed to answer the question (as judged by the reference answer).

    Args:
        retrieved_chunk_ids: IDs of retrieved chunks.
        reference_answer: Ground truth reference answer.
        chunk_texts: Map of chunk_id → chunk text.

    Returns:
        Context recall in [0, 1].
    """
    if not reference_answer or not retrieved_chunk_ids:
        return 0.0

    reference_tokens = _tokenize(reference_answer)
    if not reference_tokens:
        return 0.0

    retrieved_tokens: set[str] = set()
    for cid in retrieved_chunk_ids:
        retrieved_tokens |= _tokenize(chunk_texts.get(cid, ""))

    return len(reference_tokens & retrieved_tokens) / len(reference_tokens)
