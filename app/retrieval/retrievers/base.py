"""Abstract retriever interface.

All retrieval methods go through this interface. Business logic
depends only on Retriever — never on a concrete implementation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.retrieval.schemas import RetrievalCandidate


class Retriever(ABC):
    """Abstract retriever interface.

    All methods are async. Implementations handle connection management,
    retry, and error conversion internally.
    """

    @abstractmethod
    async def retrieve(
        self,
        query: str,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[RetrievalCandidate]:
        """Retrieve top-k results for a query.

        Args:
            query: Search query text.
            top_k: Number of results to return.
            filters: Optional metadata filters.
            **kwargs: Retriever-specific parameters.

        Returns:
            List of RetrievalCandidate ordered by relevance (descending).
        """
        ...

    @abstractmethod
    async def retrieve_batch(
        self,
        queries: list[str],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[list[RetrievalCandidate]]:
        """Retrieve top-k results for multiple queries.

        Args:
            queries: List of search queries.
            top_k: Number of results per query.
            filters: Optional metadata filters.
            **kwargs: Retriever-specific parameters.

        Returns:
            List of results per query, each ordered by relevance.
        """
        ...

    @abstractmethod
    def retriever_name(self) -> str:
        """Get the retriever name identifier."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the retriever is operational."""
        ...
