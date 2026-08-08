"""Hybrid retriever — combines dense and BM25 results via Reciprocal Rank Fusion (RRF).

Key improvements over naive sequential hybrid:
  - asyncio.gather for true parallel dense+BM25 execution
  - Score normalization (min-max) before fusion to prevent scale bias
  - Weighted RRF: configurable dense vs. sparse weight
  - Recency boosting: recent documents can be optionally up-ranked
  - Per-source score preserved for downstream diagnostics
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.core.logging import get_logger
from app.retrieval.metrics import RetrievalTimer
from app.retrieval.retrievers.base import Retriever
from app.retrieval.retrievers.bm25 import BM25Retriever
from app.retrieval.retrievers.dense import DenseRetriever
from app.retrieval.schemas import RetrievalCandidate

logger = get_logger(__name__)

# RRF smoothing constant (Cormack & Bauer, 2009)
_RRF_K = 60


def _min_max_normalize(scores: dict[str, float]) -> dict[str, float]:
    """Normalize scores into [0, 1] via min-max scaling."""
    if not scores:
        return {}
    vals = list(scores.values())
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return dict.fromkeys(scores, 1.0)
    span = hi - lo
    return {k: (v - lo) / span for k, v in scores.items()}


class HybridRetriever(Retriever):
    """Hybrid retriever: parallel dense+BM25 via Reciprocal Rank Fusion.

    Runs both retrievers concurrently with asyncio.gather, normalizes
    individual scores, then fuses with RRF weighted by ``alpha``.

    Usage:
        hybrid = HybridRetriever(dense, bm25, alpha=0.6)
        results = await hybrid.retrieve("query text", top_k=10)
    """

    def __init__(
        self,
        dense_retriever: DenseRetriever,
        bm25_retriever: BM25Retriever,
        alpha: float = 0.6,
        recency_boost: float = 0.0,
    ) -> None:
        self._dense = dense_retriever
        self._bm25 = bm25_retriever
        self._alpha = alpha  # 0 = pure BM25, 1 = pure dense
        self._recency_boost = recency_boost  # 0 = off, 0.1-0.3 = mild boost

    async def retrieve(
        self,
        query: str,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[RetrievalCandidate]:
        """Retrieve top-k results using parallel hybrid dense+BM25 search.

        Args:
            query: Search query text.
            top_k: Number of results to return after fusion.
            filters: Metadata filters forwarded to dense search.
            **kwargs:
                alpha: Dense weight override (0 = BM25, 1 = dense).
                bm25_top_k: BM25 candidate count (default top_k × 3).
                collection_name: Milvus collection override.
                recency_boost: Recency up-rank factor override.

        Returns:
            Fused, sorted list of RetrievalCandidate (length ≤ top_k).
        """
        alpha = kwargs.pop("alpha", self._alpha)
        recency_boost = kwargs.pop("recency_boost", self._recency_boost)
        bm25_top_k = kwargs.pop("bm25_top_k", top_k * 3)
        dense_top_k = max(top_k, bm25_top_k)

        with RetrievalTimer("hybrid.retrieve", tags={"alpha": str(alpha)}):
            # ── Parallel retrieval ─────────────────────────────────────────
            dense_task = self._dense.retrieve(
                query=query,
                top_k=dense_top_k,
                filters=filters,
                **kwargs,
            )
            bm25_task = self._bm25.retrieve(
                query=query,
                top_k=bm25_top_k,
                filters=filters,
            )

            try:
                with RetrievalTimer("hybrid.parallel_fetch"):
                    dense_results, bm25_results = await asyncio.gather(dense_task, bm25_task)
            except Exception as e:
                logger.warning("Parallel retrieval partial failure", error=str(e))
                # Try to get at least one result set
                dense_results = await self._dense.retrieve(
                    query=query, top_k=dense_top_k, filters=filters, **kwargs
                )
                bm25_results = []

            # ── RRF fusion with normalization ──────────────────────────────
            with RetrievalTimer("hybrid.rrf_fusion"):
                merged = self._rrf_fusion(
                    dense_results=dense_results,
                    bm25_results=bm25_results,
                    alpha=alpha,
                    recency_boost=recency_boost,
                )

        logger.debug(
            "Hybrid retrieval complete",
            query_preview=query[:60],
            dense_results=len(dense_results),
            bm25_results=len(bm25_results),
            merged=min(len(merged), top_k),
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
        """Retrieve for multiple queries concurrently."""
        tasks = [self.retrieve(q, top_k=top_k, filters=filters, **kwargs) for q in queries]
        return list(await asyncio.gather(*tasks))

    def retriever_name(self) -> str:
        return "hybrid"

    async def health_check(self) -> bool:
        dense_ok, bm25_ok = await asyncio.gather(
            self._dense.health_check(),
            self._bm25.health_check(),
        )
        return dense_ok and bm25_ok

    @property
    def dense(self) -> DenseRetriever:
        return self._dense

    @property
    def bm25(self) -> BM25Retriever:
        return self._bm25

    # ── RRF Fusion ─────────────────────────────────────────────────────────

    def _rrf_fusion(
        self,
        dense_results: list[RetrievalCandidate],
        bm25_results: list[RetrievalCandidate],
        alpha: float,
        recency_boost: float = 0.0,
    ) -> list[RetrievalCandidate]:
        """Fuse two ranked lists with Reciprocal Rank Fusion.

        Steps:
            1. Min-max normalize raw scores within each list
            2. Assign RRF rank scores
            3. Weighted combination: alpha * dense_rrf + (1-alpha) * bm25_rrf
            4. Optional recency boost from document creation date metadata

        Args:
            dense_results: Dense retriever results.
            bm25_results: BM25 retriever results.
            alpha: Dense weight [0, 1].
            recency_boost: Recency up-rank multiplier (0 = disabled).

        Returns:
            Merged, sorted list of candidates.
        """
        # Raw score maps for normalization
        dense_raw = {r.chunk_id: r.score for r in dense_results}
        bm25_raw = {r.chunk_id: r.score for r in bm25_results}

        # Normalize within each list (eliminates scale difference)
        dense_norm = _min_max_normalize(dense_raw)
        bm25_norm = _min_max_normalize(bm25_raw)

        # Rank positions (1-indexed)
        dense_ranks = {r.chunk_id: idx + 1 for idx, r in enumerate(dense_results)}
        bm25_ranks = {r.chunk_id: idx + 1 for idx, r in enumerate(bm25_results)}

        # Penalty for absence — rank beyond the actual list length
        dense_absence_rank = len(dense_results) + _RRF_K + 1
        bm25_absence_rank = len(bm25_results) + _RRF_K + 1

        all_chunk_ids = set(dense_ranks) | set(bm25_ranks)

        rrf_scores: dict[str, float] = {}
        for chunk_id in all_chunk_ids:
            dense_rank = dense_ranks.get(chunk_id, dense_absence_rank)
            bm25_rank = bm25_ranks.get(chunk_id, bm25_absence_rank)

            dense_rrf = 1.0 / (_RRF_K + dense_rank)
            bm25_rrf = 1.0 / (_RRF_K + bm25_rank)

            rrf_scores[chunk_id] = alpha * dense_rrf + (1.0 - alpha) * bm25_rrf

        # Optionally apply recency boost
        if recency_boost > 0:
            rrf_scores = self._apply_recency_boost(
                rrf_scores, dense_results + bm25_results, boost=recency_boost
            )

        sorted_ids = sorted(rrf_scores, key=lambda cid: rrf_scores[cid], reverse=True)

        # Build output candidates, preserving richer metadata (prefer dense)
        dense_map: dict[str, RetrievalCandidate] = {r.chunk_id: r for r in dense_results}
        bm25_map: dict[str, RetrievalCandidate] = {r.chunk_id: r for r in bm25_results}

        merged: list[RetrievalCandidate] = []
        for chunk_id in sorted_ids:
            candidate = dense_map.get(chunk_id) or bm25_map.get(chunk_id)
            if candidate is None:
                continue

            rrf_score = rrf_scores[chunk_id]

            # Preserve individual scores in metadata for diagnostics
            candidate.metadata["dense_score"] = dense_norm.get(chunk_id, 0.0)
            candidate.metadata["bm25_score"] = bm25_norm.get(chunk_id, 0.0)
            candidate.metadata["rrf_score"] = round(rrf_score, 6)

            # Set primary score to normalized RRF
            candidate.score = rrf_score

            if chunk_id in dense_map and chunk_id in bm25_map:
                candidate.retrieval_source = "hybrid"
            elif chunk_id in dense_map:
                candidate.retrieval_source = "dense"
            else:
                candidate.retrieval_source = "bm25"

            merged.append(candidate)

        return merged

    @staticmethod
    def _apply_recency_boost(
        scores: dict[str, float],
        candidates: list[RetrievalCandidate],
        boost: float,
    ) -> dict[str, float]:
        """Boost scores for recently created/modified documents.

        Expects metadata key ``created_at`` as an ISO date string or Unix ts.
        Documents without date metadata are not boosted.
        """
        import time as _time

        _now = _time.time()
        # Collect available timestamps
        timestamps: dict[str, float] = {}
        seen: set[str] = set()
        for c in candidates:
            if c.chunk_id in seen:
                continue
            seen.add(c.chunk_id)
            for key in ("created_at", "modified_date", "date", "published_at"):
                raw = c.metadata.get(key)
                if raw is None:
                    continue
                try:
                    if isinstance(raw, (int, float)):
                        timestamps[c.chunk_id] = float(raw)
                    elif isinstance(raw, str):
                        import datetime

                        # Try ISO parse
                        dt = datetime.datetime.fromisoformat(raw.rstrip("Z"))
                        timestamps[c.chunk_id] = dt.timestamp()
                    break
                except Exception:
                    continue

        if not timestamps:
            return scores

        # Normalise age: 0 = oldest, 1 = newest
        min_ts = min(timestamps.values())
        max_ts = max(timestamps.values())
        span = max(max_ts - min_ts, 1)

        boosted = dict(scores)
        for chunk_id, ts in timestamps.items():
            if chunk_id not in boosted:
                continue
            recency_factor = (ts - min_ts) / span  # 0 = oldest, 1 = newest
            boosted[chunk_id] = scores[chunk_id] * (1.0 + boost * recency_factor)

        return boosted
