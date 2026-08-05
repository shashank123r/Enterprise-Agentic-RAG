"""RAGEvaluator — orchestrates end-to-end RAG pipeline evaluation.

Runs a golden dataset through the retrieval and generation pipelines,
collects per-query metrics, and produces an aggregated EvaluationReport.

Usage:
    evaluator = RAGEvaluator(retrieval_service, orchestrator)
    report = await evaluator.evaluate(golden_queries, ks=[1, 3, 5, 10])
    print(report.as_dict())
"""

from __future__ import annotations

import time
from typing import Any, Sequence

from app.core.logging import get_logger
from app.evaluation.metrics import (
    answer_relevancy_score,
    average_precision,
    context_precision,
    context_recall,
    faithfulness_score,
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
from app.rag.grounding import GroundingValidator

logger = get_logger(__name__)


class RAGEvaluator:
    """Evaluates the full RAG pipeline against a golden dataset.

    Supports:
    - Retrieval-only evaluation (no LLM calls needed)
    - Generation evaluation (requires full RAG orchestrator)
    - Selective evaluation (skip generation if no reference answer)

    Args:
        retrieval_service: Initialized RetrievalService for retrieval eval.
        orchestrator: RAGOrchestrator for generation eval (optional).
        retrieval_kwargs: Default kwargs forwarded to retrieval_service.search().
        generation_kwargs: Default kwargs forwarded to orchestrator.answer().
    """

    def __init__(
        self,
        retrieval_service: Any | None = None,
        orchestrator: Any | None = None,
        retrieval_kwargs: dict[str, Any] | None = None,
        generation_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self._retrieval = retrieval_service
        self._orchestrator = orchestrator
        self._retrieval_kwargs = retrieval_kwargs or {}
        self._generation_kwargs = generation_kwargs or {}
        self._grounding_validator = GroundingValidator()

    async def evaluate(
        self,
        golden_queries: Sequence[GoldenQuery],
        ks: Sequence[int] = (1, 3, 5, 10),
        run_retrieval: bool = True,
        run_generation: bool = True,
        run_metadata: dict[str, Any] | None = None,
    ) -> EvaluationReport:
        """Run evaluation on a golden dataset.

        Args:
            golden_queries: Annotated queries with ground truth.
            ks: Cutoff values for Recall@K, Precision@K, nDCG@K.
            run_retrieval: Evaluate retrieval metrics.
            run_generation: Evaluate generation metrics (requires orchestrator).
            run_metadata: Optional dict stored in the report for provenance.

        Returns:
            EvaluationReport with per-query and aggregated metrics.
        """
        if not golden_queries:
            logger.warning("No golden queries provided — returning empty report")
            return EvaluationReport(run_metadata=run_metadata or {})

        results: list[EvaluationResult] = []

        for query in golden_queries:
            retrieval_result: RetrievalEvalResult | None = None
            generation_result: GenerationEvalResult | None = None

            # ── Retrieval evaluation ───────────────────────────────────────
            if run_retrieval and self._retrieval is not None:
                retrieval_result = await self._eval_retrieval(query, ks=ks)

            # ── Generation evaluation ──────────────────────────────────────
            if run_generation and self._orchestrator is not None and query.reference_answer:
                chunk_texts = {}
                if retrieval_result:
                    chunk_texts = {
                        cid: ""  # Actual texts filled in below
                        for cid in retrieval_result.retrieved_chunk_ids
                    }
                generation_result = await self._eval_generation(
                    query,
                    retrieved_chunk_ids=(
                        retrieval_result.retrieved_chunk_ids if retrieval_result else []
                    ),
                    chunk_texts=chunk_texts,
                )

            results.append(
                EvaluationResult(
                    golden=query,
                    retrieval=retrieval_result,
                    generation=generation_result,
                )
            )

        return self._aggregate(results, ks=ks, run_metadata=run_metadata or {})

    async def _eval_retrieval(
        self,
        query: GoldenQuery,
        ks: Sequence[int],
    ) -> RetrievalEvalResult:
        """Evaluate retrieval for a single golden query."""
        start = time.monotonic()
        retrieved_ids: list[str] = []

        try:
            max_k = max(ks)
            result = await self._retrieval.search(
                query=query.question,
                top_k=max_k,
                **self._retrieval_kwargs,
            )
            retrieved_ids = [c.chunk_id for c in result.chunks]
        except Exception as e:
            logger.warning("Retrieval eval failed for query", query_id=query.query_id, error=str(e))

        latency_ms = (time.monotonic() - start) * 1000
        relevant = query.relevant_chunk_ids or query.relevant_doc_ids

        # Compute all K-level metrics
        r_at_k = {k: recall_at_k(retrieved_ids, relevant, k) for k in ks}
        p_at_k = {k: precision_at_k(retrieved_ids, relevant, k) for k in ks}
        n_at_k = {k: ndcg_at_k(retrieved_ids, relevant, k) for k in ks}
        ap = average_precision(retrieved_ids, relevant)
        rr = (
            1.0 / (retrieved_ids.index(relevant[0]) + 1)
            if relevant and relevant[0] in retrieved_ids
            else 0.0
        )

        return RetrievalEvalResult(
            query_id=query.query_id,
            question=query.question,
            recall_at_k=r_at_k,
            precision_at_k=p_at_k,
            ndcg_at_k=n_at_k,
            reciprocal_rank=rr,
            average_precision=ap,
            retrieved_chunk_ids=retrieved_ids,
            relevant_retrieved=len(set(retrieved_ids) & set(relevant)),
            total_relevant=len(relevant),
            latency_ms=round(latency_ms, 2),
        )

    async def _eval_generation(
        self,
        query: GoldenQuery,
        retrieved_chunk_ids: list[str],
        chunk_texts: dict[str, str],
    ) -> GenerationEvalResult:
        """Evaluate generation for a single golden query."""
        start = time.monotonic()
        generated = ""
        token_usage: dict[str, int] = {}
        grounding_conf = 0.0

        try:
            rag_response = await self._orchestrator.answer(
                question=query.question,
                stream=False,
                **self._generation_kwargs,
            )
            generated = rag_response.answer
            token_usage = {
                "prompt_tokens": rag_response.prompt_tokens,
                "completion_tokens": rag_response.completion_tokens,
                "total_tokens": rag_response.total_tokens,
            }

            # Grounding confidence from the response validator
            from app.retrieval.schemas import RetrievedChunk

            chunks_for_grounding = [
                RetrievedChunk(
                    chunk_id=cid,
                    document_id="",
                    text=chunk_texts.get(cid, ""),
                    score=1.0,
                )
                for cid in retrieved_chunk_ids
            ]
            grounding_result = await self._grounding_validator.validate(
                answer=generated,
                chunks=chunks_for_grounding,
                question=query.question,
            )
            grounding_conf = grounding_result.get("confidence", 0.0)

        except Exception as e:
            logger.warning("Generation eval failed", query_id=query.query_id, error=str(e))

        latency_ms = (time.monotonic() - start) * 1000

        # Compute generation metrics
        source_texts = list(chunk_texts.values()) if chunk_texts else []
        faith = faithfulness_score(generated, source_texts)
        relevancy = answer_relevancy_score(generated, query.question)
        cp = context_precision(retrieved_chunk_ids, generated, chunk_texts)
        cr = context_recall(retrieved_chunk_ids, query.reference_answer, chunk_texts)

        # Citation coverage
        from app.rag.grounding import GroundingValidator
        from app.rag.grounding import _split_sentences

        sentences = _split_sentences(generated)
        import re

        citations_per_sentence = [1 if re.search(r"\[\d+\]", s) else 0 for s in sentences]
        citation_cov = sum(citations_per_sentence) / max(len(sentences), 1)

        return GenerationEvalResult(
            query_id=query.query_id,
            question=query.question,
            generated_answer=generated,
            reference_answer=query.reference_answer,
            faithfulness=round(faith, 4),
            answer_relevancy=round(relevancy, 4),
            context_precision=round(cp, 4),
            context_recall=round(cr, 4),
            grounding_confidence=round(grounding_conf, 4),
            citation_coverage=round(citation_cov, 4),
            latency_ms=round(latency_ms, 2),
            token_usage=token_usage,
        )

    @staticmethod
    def _aggregate(
        results: list[EvaluationResult],
        ks: Sequence[int],
        run_metadata: dict[str, Any],
    ) -> EvaluationReport:
        """Macro-average all per-query metrics into a report."""
        report = EvaluationReport(
            total_queries=len(results),
            results=results,
            run_metadata=run_metadata,
        )

        ret_results = [r.retrieval for r in results if r.retrieval]
        gen_results = [r.generation for r in results if r.generation]

        if ret_results:
            for k in ks:
                report.mean_recall[k] = round(
                    sum(r.recall_at_k.get(k, 0) for r in ret_results) / len(ret_results), 4
                )
                report.mean_precision[k] = round(
                    sum(r.precision_at_k.get(k, 0) for r in ret_results) / len(ret_results), 4
                )
                report.mean_ndcg[k] = round(
                    sum(r.ndcg_at_k.get(k, 0) for r in ret_results) / len(ret_results), 4
                )
            report.mean_reciprocal_rank = round(
                sum(r.reciprocal_rank for r in ret_results) / len(ret_results), 4
            )
            report.mean_average_precision = round(
                sum(r.average_precision for r in ret_results) / len(ret_results), 4
            )
            report.mean_retrieval_latency_ms = round(
                sum(r.latency_ms for r in ret_results) / len(ret_results), 2
            )

        if gen_results:
            report.mean_faithfulness = round(
                sum(r.faithfulness for r in gen_results) / len(gen_results), 4
            )
            report.mean_answer_relevancy = round(
                sum(r.answer_relevancy for r in gen_results) / len(gen_results), 4
            )
            report.mean_context_precision = round(
                sum(r.context_precision for r in gen_results) / len(gen_results), 4
            )
            report.mean_context_recall = round(
                sum(r.context_recall for r in gen_results) / len(gen_results), 4
            )
            report.mean_grounding_confidence = round(
                sum(r.grounding_confidence for r in gen_results) / len(gen_results), 4
            )
            report.mean_generation_latency_ms = round(
                sum(r.latency_ms for r in gen_results) / len(gen_results), 2
            )
            all_tokens = sum(r.token_usage.get("total_tokens", 0) for r in gen_results)
            report.mean_tokens_per_query = round(all_tokens / len(gen_results), 1)

        return report
