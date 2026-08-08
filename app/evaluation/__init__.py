"""RAG evaluation framework — Recall@K, Precision@K, MRR, nDCG, Faithfulness, and more."""

from app.evaluation.evaluator import RAGEvaluator
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
from app.evaluation.schemas import (
    EvaluationReport,
    EvaluationResult,
    GenerationEvalResult,
    GoldenQuery,
    RetrievalEvalResult,
)

__all__ = [
    "EvaluationReport",
    "EvaluationResult",
    "GenerationEvalResult",
    "GoldenQuery",
    "RAGEvaluator",
    "RetrievalEvalResult",
    "answer_relevancy_score",
    "average_precision",
    "context_precision",
    "context_recall",
    "faithfulness_score",
    "mean_average_precision",
    "mean_reciprocal_rank",
    "ndcg_at_k",
    "precision_at_k",
    "recall_at_k",
]
