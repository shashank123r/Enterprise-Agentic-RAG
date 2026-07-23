"""Hybrid retriever — combines dense and BM25 results via Reciprocal Rank Fusion (RRF).

Configurable dense/BM25 weighting. Dense captures semantic similarity;
BM25 captures keyword matching. RRF merges both into a single ranked list.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.retrieval.metrics import RetrievalTimer
from app.retrieval.retrievers.base import Retriever
from app.retrieval.retrievers.bm25 import BM25Retriever
from app.retrieval.retrievers.dense import DenseRetriever
from app.retrieval.schemas import RetrievalCandidate

logger = get_logger(__name__)

# RRF constant — prevents division by zero
_RRF_K = 60


class HybridRetriever(Retriever):
    """Hybrid retriever using Reciprocal Rank Fusion (RRF).

    Merges dense vector search results with BM25 keyword results
    using configurable weighting.

    Usage:
        hybrid = HybridRetriever(dense_retriever, bm25_retriever, alpha=0.5)
        results = await hybrid.retrieve("query text", top_k=10)
    """

    def __init__(
        self,
        dense_retriever: DenseRetriever,
        bm25_retriever: BM25Retriever,
        alpha: float = 0.5,
    ) -> None:
        self._dense = dense_retriever
        self._bm25 = bm25_retriever
        self._alpha = alpha  # 0 = BM25, 1 = dense

    async def retrieve(
        self,
        query: str,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[RetrievalCandidate]:
        """Retrieve top-k results using hybrid dense+BM25 search.

        Args:
            query: Search query text.
            top_k: Number of results to return.
            filters: Optional metadata filters applied to dense search.
            **kwargs: Additional parameters:
                alpha: Dense weight override (0.0 = BM25, 1.0 = dense).
                collection_name: Override for dense search collection.
                bm25_top_k: Override for BM25 candidate count.

        Returns:
            List of RetrievalCandidate merged via RRF.

        Raises:
            RetrieverUnavailable: If either sub-retriever fails.
        """
        alpha = kwargs.get("alpha", self._alpha)

        with RetrievalTimer("hybrid.retrieve", tags={"alpha": str(alpha)}):
            # Run dense and BM25 in parallel
            bm25_top_k = kwargs.get("bm25_top_k", top_k * 3)  # More candidates from BM25

            # Execute both retrievers
            with RetrievalTimer("hybrid.dense_search"):
                dense_results = await self._dense.retrieve(
                    query=query,
                    top_k=max(top_k, bm25_top_k),
                    filters=filters,
                    **kwargs,
                )

            with RetrievalTimer("hybrid.bm25_search"):
                bm25_results = await self._bm25.retrieve(
                    query=query,
                    top_k=bm25_top_k,
                    filters=filters,
                )

            # Merge via RRF
            with RetrievalTimer("hybrid.rrf_fusion"):
                merged = self._rrf_fusion(
                    dense_results=dense_results,
                    bm25_results=bm25_results,
                    alpha=alpha,
                )

            # Apply overall score threshold and return top_k
            for candidate in merged:
                if candidate.rerank_score is not None:
                    candidate.score = candidate.rerank_score

            logger.debug(
                "Hybrid retrieval complete",
                query_preview=query[:50],
                dense_results=len(dense_results),
                bm25_results=len(bm25_results),
                merged=len(merged[:top_k]),
                alpha=alpha,
            )
            return merged[:top_k]

    async def retrieve_batch(
        self,
        queries: list[str],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[list[RetrievalCandidate]]:
        """Retrieve for multiple queries."""
        results = []
        for query in queries:
            results.append(await self.retrieve(query, top_k=top_k, filters=filters, **kwargs))
        return results

    def retriever_name(self) -> str:
        return "hybrid"

    async def health_check(self) -> bool:
        """Check if both sub-retrievers are operational."""
        dense_ok = await self._dense.health_check()
        bm25_ok = await self._bm25.health_check()
        return dense_ok and bm25_ok

    @property
    def dense(self) -> DenseRetriever:
        """Access the underlying dense retriever."""
        return self._dense

    @property
    def bm25(self) -> BM25Retriever:
        """Access the underlying BM25 retriever."""
        return self._bm25

    # ── RRF Fusion ─────────────────────────────

    def _rrf_fusion(
        self,
        dense_results: list[RetrievalCandidate],
        bm25_results: list[RetrievalCandidate],
        alpha: float,
    ) -> list[RetrievalCandidate]:
        """Merge two ranked lists using Reciprocal Rank Fusion.

        Each candidate's RRF score is:
            dense_weight * 1/(rank_dense + K) + (1-dense_weight) * 1/(rank_bm25 + K)

        Args:
            dense_results: Results from dense retriever (ranked).
            bm25_results: Results from BM25 retriever (ranked).
            alpha: Dense weight (0.0 to 1.0).

        Returns:
            Merged list sorted by combined RRF score (descending).
        """
        # Build rank maps: chunk_id -> rank position (1-indexed)
        dense_ranks = {r.chunk_id: idx + 1 for idx, r in enumerate(dense_results)}
        bm25_ranks = {r.chunk_id: idx + 1 for idx, r in enumerate(bm25_results)}

        # Collect unique chunk IDs from both result sets
        all_chunk_ids = set(dense_ranks.keys()) | set(bm25_ranks.keys())

        # Compute RRF scores
        rrf_scores: dict[str, float] = {}
        for chunk_id in all_chunk_ids:
            dense_rank = dense_ranks.get(chunk_id, _RRF_K * 10)  # Large penalty if absent
            bm25_rank = bm25_ranks.get(chunk_id, _RRF_K * 10)

            dense_rrf = 1.0 / (_RRF_K + dense_rank)
            bm25_rrf = 1.0 / (_RRF_K + bm25_rank)

            rrf_scores[chunk_id] = alpha * dense_rrf + (1 - alpha) * bm25_rrf

        # Sort by RRF score descending
        sorted_ids = sorted(rrf_scores, key=lambda cid: rrf_scores[cid], reverse=True)

        # Build merged results — prefer dense candidate for richer metadata
        merged: list[RetrievalCandidate] = []
        seen = set()
        for chunk_id in sorted_ids:
            if chunk_id in seen:
                continue
            seen.add(chunk_id)

            # Find the best candidate (prefer dense for metadata)
            dense_candidate = next((r for r in dense_results if r.chunk_id == chunk_id), None)
            bm25_candidate = next((r for r in bm25_results if r.chunk_id == chunk_id), None)

            candidate: RetrievalCandidate | None = None
            if dense_candidate and bm25_candidate:
                # Merge: use dense metadata but update score to RRF
                candidate = dense_candidate
                candidate.rerank_score = bm25_candidate.score
                candidate.score = rrf_scores[chunk_id]
                candidate.retrieval_source = "hybrid"
            elif dense_candidate:
                candidate = dense_candidate
                candidate.score = rrf_scores[chunk_id]
                candidate.retrieval_source = "dense"
            elif bm25_candidate:
                candidate = bm25_candidate
                candidate.score = rrf_scores[chunk_id]
                candidate.retrieval_source = "bm25"

            if candidate:
                merged.append(candidate)

        return merged
