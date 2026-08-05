"""RAG evaluation framework — Recall@K, Precision@K, MRR, nDCG, Faithfulness, and more."""

from app.evaluation.metrics import (
    recall_at_k,
    precision_at_k,
    mean_reciprocal_rank,
    ndcg_at_k,
    average_precision,
    mean_average_precision,
    faithfulness_score,
    answer_relevancy_score,
    context_precision,
    context_recall,
)
from app.evaluation.evaluator import RAGEvaluator
from app.evaluation.schemas import (
    GoldenQuery,
    EvaluationResult,
    RetrievalEvalResult,
    GenerationEvalResult,
    EvaluationReport,
)

__all__ = [
    "recall_at_k",
    "precision_at_k",
    "mean_reciprocal_rank",
    "ndcg_at_k",
    "average_precision",
    "mean_average_precision",
    "faithfulness_score",
    "answer_relevancy_score",
    "context_precision",
    "context_recall",
    "RAGEvaluator",
    "GoldenQuery",
    "EvaluationResult",
    "RetrievalEvalResult",
    "GenerationEvalResult",
    "EvaluationReport",
]
