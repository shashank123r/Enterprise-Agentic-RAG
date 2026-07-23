"""Abstract reranker interface.

All reranking operations go through this interface. Business logic
depends only on Reranker — never on a concrete implementation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.retrieval.schemas import RetrievalCandidate


class Reranker(ABC):
    """Abstract reranker interface.

    Takes a list of retrieval candidates and returns them reordered
    by relevance score (descending).

    All methods are async. Implementations handle API calls, retries,
    and error conversion internally.
    """

    @abstractmethod
    async def rerank(
        self,
        query: str,
        candidates: list[RetrievalCandidate],
        top_k: int | None = None,
        **kwargs: Any,
    ) -> list[RetrievalCandidate]:
        """Rerank a list of candidates by relevance to the query.

        Args:
            query: Original search query.
            candidates: List of candidates to rerank.
            top_k: If set, return only top-k after reranking.
            **kwargs: Provider-specific parameters.

        Returns:
            Reranked candidates sorted by relevance (descending).
            Each candidate has ``rerank_score`` set to the reranker score.
        """
        ...

    @abstractmethod
    async def rerank_batch(
        self,
        queries: list[str],
        candidates_batch: list[list[RetrievalCandidate]],
        top_k: int | None = None,
        **kwargs: Any,
    ) -> list[list[RetrievalCandidate]]:
        """Rerank multiple query-candidate pairs.

        Args:
            queries: List of queries (same length as candidates_batch).
            candidates_batch: List of candidate lists (same length as queries).
            top_k: If set, return only top-k after reranking.

        Returns:
            Reranked candidate lists.
        """
        ...

    @abstractmethod
    def reranker_name(self) -> str:
        """Get the reranker name identifier."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the reranker is operational."""
        ...
