"""Parent-Child retriever — retrieves parent documents from matching chunks.

After performing dense or hybrid retrieval at the chunk level, this
retriever groups results by document and returns document-level results
with aggregated metadata and scores.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.core.logging import get_logger
from app.retrieval.metrics import RetrievalTimer
from app.retrieval.retrievers.base import Retriever
from app.retrieval.retrievers.hybrid import HybridRetriever
from app.retrieval.schemas import RetrievalCandidate

logger = get_logger(__name__)


class ParentChildRetriever(Retriever):
    """Retrieves chunks and groups them by parent document.

    Useful for RAG systems that need full document context rather than
    individual chunks. Returns documents with their top matching chunks.

    Usage:
        retriever = ParentChildRetriever(hybrid_retriever, max_chunks_per_doc=3)
        results = await retriever.retrieve("query", top_k=5)
    """

    def __init__(
        self,
        base_retriever: HybridRetriever,
        max_chunks_per_doc: int = 3,
    ) -> None:
        self._base = base_retriever
        self._max_chunks_per_doc = max_chunks_per_doc

    async def retrieve(
        self,
        query: str,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[RetrievalCandidate]:
        """Retrieve top-k documents (via chunk-then-group).

        1. Retrieves many chunks using the base retriever.
        2. Groups chunks by document_id.
        3. Returns the top-k documents with their best chunks.

        Args:
            query: Search query text.
            top_k: Number of documents to return.
            filters: Optional metadata filters.
            **kwargs: Additional parameters:
                chunk_top_k: Number of chunks to retrieve before grouping.

        Returns:
            List of RetrievalCandidate (one per document, with aggregated text).
        """
        chunk_top_k = kwargs.get("chunk_top_k", top_k * 3)

        with RetrievalTimer("parent_child.retrieve"):
            # Step 1: Retrieve many chunks
            with RetrievalTimer("parent_child.base_retrieve"):
                chunks = await self._base.retrieve(
                    query=query,
                    top_k=chunk_top_k,
                    filters=filters,
                    **kwargs,
                )

            if not chunks:
                return []

            # Step 2: Group by document_id
            doc_chunks: dict[str, list[RetrievalCandidate]] = defaultdict(list)
            for chunk in chunks:
                doc_chunks[chunk.document_id].append(chunk)

            # Step 3: Build document-level results
            doc_results: list[tuple[float, RetrievalCandidate]] = []
            for doc_id, doc_chunks_list in doc_chunks.items():
                # Sort chunks by score descending within document
                doc_chunks_list.sort(key=lambda c: c.score, reverse=True)

                # Take top chunks per document
                top_chunks = doc_chunks_list[: self._max_chunks_per_doc]

                # Compute document score as max chunk score (or average)
                doc_score = top_chunks[0].score

                # Combine chunk texts into a single document text
                combined_text = "\n\n".join(
                    f"[Page {c.page_number or '?'}] {c.section_title or ''}\n{c.text}"
                    for c in top_chunks
                )

                # Build document candidate with first chunk's metadata
                first = top_chunks[0]
                doc_candidate = RetrievalCandidate(
                    chunk_id=doc_id,
                    document_id=doc_id,
                    text=combined_text,
                    score=doc_score,
                    page_number=first.page_number,
                    section_title=first.section_title or f"Document with {len(top_chunks)} matching chunks",
                    chunk_index=first.chunk_index,
                    language=first.language,
                    metadata={
                        "parent_document": True,
                        "matching_chunks": len(top_chunks),
                        "total_chunks_in_document": len(doc_chunks_list),
                        **(first.metadata or {}),
                    },
                    retrieval_source="parent_child",
                )
                doc_results.append((doc_score, doc_candidate))

            # Sort by score descending, return top_k
            doc_results.sort(key=lambda x: x[0], reverse=True)

            logger.debug(
                "Parent-child retrieval complete",
                query_preview=query[:50],
                documents=len(doc_results[:top_k]),
                total_docs=len(doc_results),
                total_chunks=len(chunks),
            )
            return [result for _, result in doc_results[:top_k]]

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
        return "parent_child"

    async def health_check(self) -> bool:
        """Check if the base retriever is operational."""
        return await self._base.health_check()
