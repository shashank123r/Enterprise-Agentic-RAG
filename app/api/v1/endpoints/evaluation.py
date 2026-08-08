"""Evaluation API endpoints — run RAG evaluation and retrieve metrics."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.dependencies import get_current_user_id
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


class GoldenQueryRequest(BaseModel):
    """A single golden query for evaluation."""

    query_id: str = Field(..., description="Unique query ID")
    question: str = Field(..., min_length=1, description="Question text")
    relevant_chunk_ids: list[str] = Field(default_factory=list)
    relevant_doc_ids: list[str] = Field(default_factory=list)
    reference_answer: str = Field("", description="Human reference answer")
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationRequest(BaseModel):
    """Request to run RAG evaluation on a golden dataset."""

    golden_queries: list[GoldenQueryRequest] = Field(..., min_length=1)
    ks: list[int] = Field(default=[1, 3, 5, 10], description="K cutoffs for Recall/Precision/nDCG")
    run_retrieval: bool = Field(True, description="Evaluate retrieval metrics")
    run_generation: bool = Field(False, description="Evaluate generation (slower — calls LLM)")
    retrieval_method: str = Field("hybrid", description="Retrieval method to evaluate")
    top_k: int = Field(10, ge=1, le=50)


@router.post(
    "/run",
    summary="Run RAG evaluation",
    description="Evaluate retrieval and generation quality against a golden dataset.",
)
async def run_evaluation(
    request: EvaluationRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Run the RAG evaluation pipeline and return aggregated metrics."""
    try:
        from app.evaluation.evaluator import RAGEvaluator
        from app.evaluation.schemas import GoldenQuery

        golden_queries = [
            GoldenQuery(
                query_id=q.query_id,
                question=q.question,
                relevant_chunk_ids=q.relevant_chunk_ids,
                relevant_doc_ids=q.relevant_doc_ids,
                reference_answer=q.reference_answer,
                metadata=q.metadata,
            )
            for q in request.golden_queries
        ]

        # Prefer the app-level singleton; fall back to None (metrics-only mode)
        try:
            from app.main import _retrieval_service  # type: ignore[attr-defined]

            retrieval_svc = _retrieval_service
        except (ImportError, AttributeError):
            retrieval_svc = None

        evaluator = RAGEvaluator(
            retrieval_service=retrieval_svc,
            retrieval_kwargs={"method": request.retrieval_method, "top_k": request.top_k},
        )

        report = await evaluator.evaluate(
            golden_queries=golden_queries,
            ks=request.ks,
            run_retrieval=request.run_retrieval and retrieval_svc is not None,
            run_generation=False,  # Generation eval requires orchestrator wiring
            run_metadata={
                "method": request.retrieval_method,
                "top_k": request.top_k,
                "user_id": user_id,
            },
        )

        return report.as_dict()

    except Exception as e:
        logger.exception("Evaluation failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Evaluation failed: {e}",
        )


@router.get(
    "/metrics/definitions",
    summary="List evaluation metric definitions",
    description="Return documentation for all supported evaluation metrics.",
)
async def metric_definitions() -> dict[str, Any]:
    """Return definitions and formulas for all supported evaluation metrics."""
    return {
        "retrieval_metrics": {
            "recall_at_k": {
                "description": "Fraction of all relevant items found in top-K results",
                "range": "[0, 1]",
                "higher_is_better": True,
                "formula": "|retrieved_k ∩ relevant| / |relevant|",
            },
            "precision_at_k": {
                "description": "Fraction of top-K retrieved items that are relevant",
                "range": "[0, 1]",
                "higher_is_better": True,
                "formula": "|retrieved_k ∩ relevant| / K",
            },
            "mrr": {
                "description": "Mean Reciprocal Rank — average of 1/rank of first relevant result",
                "range": "[0, 1]",
                "higher_is_better": True,
                "formula": "mean(1 / rank_first_relevant)",
            },
            "ndcg_at_k": {
                "description": "Normalized Discounted Cumulative Gain — position-aware relevance",
                "range": "[0, 1]",
                "higher_is_better": True,
                "formula": "DCG@K / IDCG@K",
            },
            "map": {
                "description": "Mean Average Precision across all queries",
                "range": "[0, 1]",
                "higher_is_better": True,
            },
        },
        "generation_metrics": {
            "faithfulness": {
                "description": "Token overlap between answer and retrieved sources — measures hallucination",
                "range": "[0, 1]",
                "higher_is_better": True,
            },
            "answer_relevancy": {
                "description": "Coverage of question key terms in the answer",
                "range": "[0, 1]",
                "higher_is_better": True,
            },
            "context_precision": {
                "description": "Fraction of retrieved chunks that contributed to the answer",
                "range": "[0, 1]",
                "higher_is_better": True,
            },
            "context_recall": {
                "description": "Fraction of reference answer tokens covered by retrieved chunks",
                "range": "[0, 1]",
                "higher_is_better": True,
            },
            "grounding_confidence": {
                "description": "Semantic TF-IDF similarity between answer sentences and sources",
                "range": "[0, 1]",
                "higher_is_better": True,
            },
            "citation_coverage": {
                "description": "Fraction of substantive answer sentences with inline citations",
                "range": "[0, 1]",
                "higher_is_better": True,
            },
        },
    }
