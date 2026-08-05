"""ColBERT reranker — late interaction scoring for fine-grained relevance.

ColBERT uses a late interaction mechanism that computes token-level
similarities between query and document tokens. This is more accurate
than bi-encoder retrieval but cheaper than full cross-encoders.

This implementation calls a ColBERT-compatible API endpoint (NVIDIA NIM
or a local ColBERT server).
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.retrieval.exceptions import RerankerError, RerankerUnavailable
from app.retrieval.metrics import RetrievalTimer
from app.retrieval.rerankers.base import Reranker
from app.retrieval.schemas import RetrievalCandidate

logger = get_logger(__name__)


class ColBERTReranker(Reranker):
    """ColBERT late-interaction reranker.

    Uses a ColBERT-compatible API for token-level relevance scoring.
    Falls back gracefully if the API is unavailable.

    Usage:
        reranker = ColBERTReranker()
        reranked = await reranker.rerank(query, candidates, top_k=5)
    """

    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        model: str = "colbertv2",
        timeout: int = 60,
        max_chunks_per_request: int = 50,
    ) -> None:
        self._api_url = (api_url or f"{str(settings.NIM_RERANKING_URL)}/colbert").rstrip("/")
        self._api_key = api_key or settings.NIM_API_KEY
        self._model = model
        self._timeout = timeout
        self._max_chunks_per_request = max_chunks_per_request
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
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
        """Rerank candidates using ColBERT late interaction.

        Args:
            query: Original search query.
            candidates: List of candidates to rerank.
            top_k: If set, return top-k after reranking.

        Returns:
            Reranked candidates sorted by relevance (descending).

        Raises:
            RerankerUnavailable: If the ColBERT endpoint is unreachable.
        """
        if not candidates:
            return []

        top_k = top_k or len(candidates)
        candidates_to_rerank = candidates[: self._max_chunks_per_request]

        with RetrievalTimer("colbert.rerank"):
            try:
                passages = [c.text for c in candidates_to_rerank]
                payload = {
                    "query": query,
                    "passages": passages,
                    "model": self._model,
                }

                response = await self.client.post(
                    f"{self._api_url}/score",
                    json=payload,
                )

                if response.status_code != 200:
                    raise RerankerError(f"ColBERT API returned HTTP {response.status_code}")

                data = response.json()
                scores = data.get("scores", data.get("results", []))

                reranked = []
                for idx, score in enumerate(scores):
                    if idx < len(candidates_to_rerank):
                        candidate = candidates_to_rerank[idx]
                        score_val = (
                            score if isinstance(score, (int, float)) else score.get("score", 0.0)
                        )
                        candidate.rerank_score = score_val
                        candidate.score = score_val
                        candidate.retrieval_source = f"{candidate.retrieval_source}_reranked"
                        reranked.append(candidate)

                reranked.sort(key=lambda c: c.rerank_score or 0.0, reverse=True)

                logger.debug(
                    "ColBERT reranking complete",
                    candidates_in=len(candidates),
                    candidates_out=len(reranked[:top_k]),
                )
                return reranked[:top_k]

            except httpx.TimeoutException:
                raise RerankerUnavailable("ColBERT reranking request timed out")
            except httpx.ConnectError as e:
                raise RerankerUnavailable(f"Cannot connect to ColBERT endpoint: {e}")
            except Exception as e:
                raise RerankerError(f"ColBERT reranking failed: {e}")

    async def rerank_batch(
        self,
        queries: list[str],
        candidates_batch: list[list[RetrievalCandidate]],
        top_k: int | None = None,
        **kwargs: Any,
    ) -> list[list[RetrievalCandidate]]:
        results = []
        for query, candidates in zip(queries, candidates_batch):
            results.append(await self.rerank(query, candidates, top_k=top_k, **kwargs))
        return results

    def reranker_name(self) -> str:
        return "colbert"

    async def health_check(self) -> bool:
        try:
            response = await self.client.get(f"{self._api_url}/health")
            return response.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
