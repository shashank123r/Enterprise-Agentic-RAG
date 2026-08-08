"""Dense retriever — Milvus vector similarity search.

Embeds the query using the configured EmbeddingProvider,
then searches Milvus for the nearest neighbors.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.embeddings.providers.base import EmbeddingProvider
from app.retrieval.exceptions import RetrievalError, RetrieverUnavailable
from app.retrieval.metrics import RetrievalTimer
from app.retrieval.retrievers.base import Retriever
from app.retrieval.schemas import RetrievalCandidate
from app.vector_stores.base import VectorStore
from app.vector_stores.exceptions import CollectionNotFound, VectorStoreUnavailable

logger = get_logger(__name__)


class DenseRetriever(Retriever):
    """Dense (vector similarity) retriever using Milvus.

    Pipeline:
        1. Embed the query via EmbeddingProvider.
        2. Search Milvus for nearest neighbors.
        3. Convert results to RetrievalCandidate list.

    Usage:
        retriever = DenseRetriever(embedding_provider, vector_store)
        results = await retriever.retrieve("query text", top_k=10)
    """

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
        collection_name: str = "documents",
    ) -> None:
        self._provider = embedding_provider
        self._store = vector_store
        self._collection_name = collection_name

    async def retrieve(
        self,
        query: str,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[RetrievalCandidate]:
        """Retrieve top-k results via dense vector search.

        Args:
            query: Search query text.
            top_k: Number of results to return.
            filters: Optional metadata filters (e.g. {'language': 'en'}).
            **kwargs: Additional parameters (collection_name override, etc.).

        Returns:
            List of RetrievalCandidate ordered by similarity (descending).

        Raises:
            RetrieverUnavailable: If Milvus or embedding provider is unavailable.
        """
        collection = kwargs.get("collection_name", self._collection_name)

        with RetrievalTimer("dense.retrieve", tags={"collection": collection}):
            try:
                # Step 1: Embed the query
                with RetrievalTimer("dense.embed_query"):
                    embedded = await self._provider.embed_query(query)
                    query_vector = embedded.vector

                # Step 2: Build filter expression from filters dict
                filter_expr = self._build_filter_expr(filters) if filters else None

                # Step 3: Search Milvus
                with RetrievalTimer("dense.vector_search"):
                    results = await self._store.search(
                        collection_name=collection,
                        query_vector=query_vector,
                        top_k=top_k,
                        filter_expr=filter_expr,
                    )

                # Step 4: Convert to candidates
                candidates = []
                for r in results:
                    candidates.append(
                        RetrievalCandidate(
                            chunk_id=r.chunk_id,
                            document_id=r.document_id,
                            text=r.text,
                            score=r.score,
                            page_number=(
                                r.metadata.get("page_number")
                                if isinstance(r.metadata, dict)
                                else None
                            ),
                            section_title=(
                                r.metadata.get("section_title")
                                if isinstance(r.metadata, dict)
                                else None
                            ),
                            chunk_index=r.chunk_index,
                            language=(
                                r.metadata.get("language") if isinstance(r.metadata, dict) else None
                            ),
                            metadata=r.metadata if isinstance(r.metadata, dict) else {},
                            retrieval_source="dense",
                        )
                    )

                logger.debug(
                    "Dense retrieval complete",
                    query_preview=query[:50],
                    top_k=top_k,
                    results=len(candidates),
                )
                return candidates

            except CollectionNotFound:
                logger.warning("Collection not found for dense search", collection=collection)
                return []
            except VectorStoreUnavailable as e:
                raise RetrieverUnavailable(f"Vector store unavailable: {e}")
            except Exception as e:
                raise RetrievalError(f"Dense retrieval failed: {e}")

    async def retrieve_batch(
        self,
        queries: list[str],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[list[RetrievalCandidate]]:
        """Retrieve for multiple queries sequentially.

        Args:
            queries: List of search queries.
            top_k: Number of results per query.
            filters: Optional metadata filters.
            **kwargs: Additional parameters.

        Returns:
            List of results per query.
        """
        results = []
        for query in queries:
            results.append(await self.retrieve(query, top_k=top_k, filters=filters, **kwargs))
        return results

    def retriever_name(self) -> str:
        return "dense"

    async def health_check(self) -> bool:
        """Check if the retriever is operational."""
        try:
            return await self._store.health_check()
        except Exception:
            return False

    @staticmethod
    def _build_filter_expr(filters: dict[str, Any]) -> str:
        """Build a Milvus filter expression from a filters dict.

        Supports exact match filters like:
            {'language': 'en', 'document_id': 'abc-123'}
            {'page_number': 5}

        Args:
            filters: Dict of field_name -> value.

        Returns:
            Milvus filter expression string (e.g., 'language == "en" && document_id == "abc-123"').
        """
        exprs = []
        for key, value in filters.items():
            if isinstance(value, str):
                exprs.append(f'{key} == "{value}"')
            elif isinstance(value, (int, float)):
                exprs.append(f"{key} == {value}")
            elif isinstance(value, bool):
                exprs.append(f"{key} == {str(value).lower()}")
            elif isinstance(value, list):
                if value:
                    vals = ", ".join(f'"{v}"' if isinstance(v, str) else str(v) for v in value)
                    exprs.append(f"{key} in [{vals}]")
            elif value is None:
                pass  # Skip None values
        return " && ".join(exprs) if exprs else ""
