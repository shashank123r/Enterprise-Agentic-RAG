"""Schemas for the RAG evaluation framework."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GoldenQuery:
    """A single annotated query for evaluation.

    Attributes:
        query_id: Unique identifier.
        question: Natural language question.
        relevant_chunk_ids: Ground truth relevant chunk IDs (for retrieval eval).
        relevant_doc_ids: Ground truth relevant document IDs.
        reference_answer: Human-written reference answer (for generation eval).
        metadata: Optional additional fields (domain, difficulty, language, etc.).
    """

    query_id: str
    question: str
    relevant_chunk_ids: list[str] = field(default_factory=list)
    relevant_doc_ids: list[str] = field(default_factory=list)
    reference_answer: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalEvalResult:
    """Per-query retrieval evaluation result."""

    query_id: str
    question: str
    recall_at_k: dict[int, float] = field(default_factory=dict)   # {k: recall}
    precision_at_k: dict[int, float] = field(default_factory=dict)
    ndcg_at_k: dict[int, float] = field(default_factory=dict)
    reciprocal_rank: float = 0.0
    average_precision: float = 0.0
    retrieved_chunk_ids: list[str] = field(default_factory=list)
    relevant_retrieved: int = 0
    total_relevant: int = 0
    latency_ms: float = 0.0


@dataclass
class GenerationEvalResult:
    """Per-query generation evaluation result."""

    query_id: str
    question: str
    generated_answer: str = ""
    reference_answer: str = ""
    faithfulness: float = 0.0          # How grounded in sources [0, 1]
    answer_relevancy: float = 0.0      # How relevant to the question [0, 1]
    context_precision: float = 0.0     # Fraction of retrieved chunks that are useful [0, 1]
    context_recall: float = 0.0        # Fraction of necessary info retrieved [0, 1]
    grounding_confidence: float = 0.0  # From GroundingValidator
    citation_coverage: float = 0.0     # Fraction of answer sentences with citations
    latency_ms: float = 0.0
    token_usage: dict[str, int] = field(default_factory=dict)


@dataclass
class EvaluationResult:
    """Combined retrieval + generation result for one query."""

    golden: GoldenQuery
    retrieval: RetrievalEvalResult | None = None
    generation: GenerationEvalResult | None = None


@dataclass
class EvaluationReport:
    """Aggregate evaluation report across all golden queries."""

    total_queries: int = 0
    # Retrieval metrics (macro-averaged)
    mean_recall: dict[int, float] = field(default_factory=dict)
    mean_precision: dict[int, float] = field(default_factory=dict)
    mean_ndcg: dict[int, float] = field(default_factory=dict)
    mean_reciprocal_rank: float = 0.0
    mean_average_precision: float = 0.0
    # Generation metrics (macro-averaged)
    mean_faithfulness: float = 0.0
    mean_answer_relevancy: float = 0.0
    mean_context_precision: float = 0.0
    mean_context_recall: float = 0.0
    mean_grounding_confidence: float = 0.0
    # Latency
    mean_retrieval_latency_ms: float = 0.0
    mean_generation_latency_ms: float = 0.0
    # Token efficiency
    mean_tokens_per_query: float = 0.0
    # Per-query results
    results: list[EvaluationResult] = field(default_factory=list)
    # Run metadata
    run_metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_queries": self.total_queries,
            "retrieval": {
                "recall": self.mean_recall,
                "precision": self.mean_precision,
                "ndcg": self.mean_ndcg,
                "mrr": round(self.mean_reciprocal_rank, 4),
                "map": round(self.mean_average_precision, 4),
                "mean_latency_ms": round(self.mean_retrieval_latency_ms, 1),
            },
            "generation": {
                "faithfulness": round(self.mean_faithfulness, 4),
                "answer_relevancy": round(self.mean_answer_relevancy, 4),
                "context_precision": round(self.mean_context_precision, 4),
                "context_recall": round(self.mean_context_recall, 4),
                "grounding_confidence": round(self.mean_grounding_confidence, 4),
                "mean_latency_ms": round(self.mean_generation_latency_ms, 1),
            },
            "efficiency": {
                "mean_tokens_per_query": round(self.mean_tokens_per_query, 1),
            },
            "run_metadata": self.run_metadata,
        }
