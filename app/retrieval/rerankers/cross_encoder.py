"""Cross-encoder reranker — uses NVIDIA NIM reranking API or a local model.

Cross-encoders jointly encode the query and each candidate document
to produce a precise relevance score. This is more accurate than
bi-encoder (dense) retrieval but slower, so it's used as a refinement
step after initial retrieval.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.retrieval.exceptions import RerankerError, RerankerUnavailable
from app.retrieval.metrics import RetrievalTimer, record_reranker_metrics
from app.retrieval.rerankers.base import Reranker
from app.retrieval.schemas import RetrievalCandidate

logger = get_logger(__name__)


class CrossEncoderReranker(Reranker):
    """Cross-encoder reranker using NVIDIA NIM or a compatible API endpoint.

    Calls the NVIDIA NIM reranking API which takes a query and a list of
    passages and returns relevance scores for each passage.

    Usage:
        reranker = CrossEncoderReranker()
        reranked = await reranker.rerank(query, candidates, top_k=5)
    """

    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int = 30,
        max_chunks_per_request: int = 100,
    ) -> None:
        # NIM_RERANKING_URL already includes /v1/rerank — use as-is, no appending
        self._api_url = (api_url or str(settings.NIM_RERANKING_URL)).rstrip("/")
        self._api_key = api_key or settings.NIM_API_KEY
        self._model = model or settings.NIM_MODEL_RERANK
        self._timeout = timeout
        self._max_chunks_per_request = max_chunks_per_request
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Lazy-initialized HTTP client."""
        if self._client is None:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"

            self._client = httpx.AsyncClient(
                headers=headers,
                timeout=httpx.Timeout(self._timeout),
            )
        return self._client

    async def rerank(
        self,
        query: str,
        candidates: list[RetrievalCandidate],
        top_k: int | None = None,
        **kwargs: Any,
    ) -> list[RetrievalCandidate]:
        """Rerank candidates using a cross-encoder.

        Args:
            query: Original search query.
            candidates: List of candidates to rerank.
            top_k: If set, return top-k after reranking.

        Returns:
            Reranked candidates sorted by reranker score (descending).

        Raises:
            RerankerUnavailable: If the NIM endpoint is unreachable.
        """
        if not candidates:
            return []

        top_k = top_k or len(candidates)
        candidates_to_rerank = candidates[: self._max_chunks_per_request]

        with RetrievalTimer("cross_encoder.rerank"):
            try:
                # Prepare payload
                passages = [c.text for c in candidates_to_rerank]
                payload = {
                    "model": self._model,
                    "query": {"text": query},
                    "passages": [{"text": p} for p in passages],
                }

                # Call the reranking API
                response = await self.client.post(
                    self._api_url,
                    json=payload,
                )

                if response.status_code != 200:
                    raise RerankerError(
                        f"Reranking API returned HTTP {response.status_code}: {response.text[:200]}"
                    )

                data = response.json()

                # Parse results
                results = data.get("results", data.get("data", []))
                if not results:
                    logger.warning("Empty reranker results")
                    return candidates[:top_k]

                # Map scores back to candidates
                reranked = []
                for result in results:
                    index = result.get("index")
                    score = result.get("score", result.get("relevance_score", 0.0))
                    if index is not None and index < len(candidates_to_rerank):
                        candidate = candidates_to_rerank[index]
                        candidate.rerank_score = score
                        candidate.score = score  # Override primary score
                        candidate.retrieval_source = f"{candidate.retrieval_source}_reranked"
                        reranked.append(candidate)

                # Sort by reranker score descending
                reranked.sort(key=lambda c: c.rerank_score or 0.0, reverse=True)

                record_reranker_metrics(
                    provider="cross_encoder",
                    duration_ms=0.0,  # Set externally via timer
                    candidates=len(candidates_to_rerank),
                )

                logger.debug(
                    "Cross-encoder reranking complete",
                    candidates_in=len(candidates),
                    candidates_out=len(reranked[:top_k]),
                )
                return reranked[:top_k]

            except httpx.TimeoutException:
                logger.warning("Reranking request timed out — returning unreranked results")
                return candidates[:top_k]
            except httpx.ConnectError as e:
                logger.warning("Cannot connect to reranking endpoint — returning unreranked results", error=str(e))
                return candidates[:top_k]
            except Exception as e:
                logger.warning("Cross-encoder reranking failed — returning unreranked results", error=str(e))
                return candidates[:top_k]

    async def rerank_batch(
        self,
        queries: list[str],
        candidates_batch: list[list[RetrievalCandidate]],
        top_k: int | None = None,
        **kwargs: Any,
    ) -> list[list[RetrievalCandidate]]:
        """Rerank multiple query-candidate pairs concurrently."""
        import asyncio
        tasks = [
            self.rerank(query, candidates, top_k=top_k, **kwargs)
            for query, candidates in zip(queries, candidates_batch)
        ]
        return list(await asyncio.gather(*tasks))

    def reranker_name(self) -> str:
        return "cross_encoder"

    async def health_check(self) -> bool:
        """Check if the reranking endpoint is reachable."""
        try:
            response = await self.client.get(f"{self._api_url}/health")
            return response.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
