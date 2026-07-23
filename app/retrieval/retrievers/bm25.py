"""BM25 keyword retriever — sparse retrieval using BM25 ranking.

Maintains an in-memory inverted index of document chunks and ranks
results using the BM25 algorithm. The index can be built from any
list of chunk dicts (typically loaded from the ingestion pipeline).

Uses a simple BM25 implementation (no external dependency required)
for production-grade sparse retrieval.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from app.core.logging import get_logger
from app.retrieval.exceptions import BM25IndexError, RetrievalError
from app.retrieval.metrics import RetrievalTimer
from app.retrieval.retrievers.base import Retriever
from app.retrieval.schemas import BM25IndexEntry, RetrievalCandidate

logger = get_logger(__name__)


class BM25Retriever(Retriever):
    """BM25 keyword retriever.

    Maintains an in-memory inverted index. The index must be built or
    updated before retrieval can be performed.

    Usage:
        retriever = BM25Retriever()
        await retriever.build_index(chunks)  # chunks from ingestion
        results = await retriever.retrieve("query text", top_k=10)
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self._k1 = k1
        self._b = b
        self._entries: list[BM25IndexEntry] = []
        self._doc_freqs: dict[str, int] = {}
        self._avg_doc_length: float = 0.0
        self._index_built = False
        self._total_docs: int = 0

    # ── Index building ─────────────────────────

    async def build_index(self, chunks: list[dict[str, Any]]) -> None:
        """Build the BM25 inverted index from a list of chunk dicts.

        Args:
            chunks: List of chunk dicts with 'text', 'chunk_id', 'document_id', etc.

        Raises:
            BM25IndexError: If index building fails.
        """
        try:
            entries: list[BM25IndexEntry] = []
            total_tokens = 0
            doc_freq_counter: Counter[str] = Counter()

            for chunk in chunks:
                text = chunk.get("text", "")
                tokens = self._tokenize(text)
                entry = BM25IndexEntry(
                    chunk_id=chunk.get("chunk_id", ""),
                    document_id=chunk.get("document_id", ""),
                    text=text,
                    tokens=tokens,
                    metadata=chunk.get("metadata", {}),
                    page_number=chunk.get("page_number"),
                    section_title=chunk.get("section_title"),
                    chunk_index=chunk.get("chunk_index", 0),
                    language=chunk.get("language"),
                )
                entries.append(entry)
                total_tokens += len(tokens)

                # Track document frequency (unique tokens per doc)
                unique_tokens = set(tokens)
                for token in unique_tokens:
                    doc_freq_counter[token] += 1

            self._entries = entries
            self._doc_freqs = dict(doc_freq_counter)
            self._total_docs = len(entries)
            self._avg_doc_length = total_tokens / max(self._total_docs, 1)
            self._index_built = True

            logger.info(
                "BM25 index built",
                total_docs=self._total_docs,
                unique_tokens=len(self._doc_freqs),
                avg_doc_length=round(self._avg_doc_length, 1),
            )

        except Exception as e:
            raise BM25IndexError(f"Failed to build BM25 index: {e}")

    async def update_index(self, chunks: list[dict[str, Any]]) -> None:
        """Add new chunks to an existing index.

        Args:
            chunks: New chunk dicts to index.
        """
        if not self._index_built:
            await self.build_index(chunks)
            return

        for chunk in chunks:
            text = chunk.get("text", "")
            tokens = self._tokenize(text)
            entry = BM25IndexEntry(
                chunk_id=chunk.get("chunk_id", ""),
                document_id=chunk.get("document_id", ""),
                text=text,
                tokens=tokens,
                metadata=chunk.get("metadata", {}),
                page_number=chunk.get("page_number"),
                section_title=chunk.get("section_title"),
                chunk_index=chunk.get("chunk_index", 0),
                language=chunk.get("language"),
            )
            self._entries.append(entry)

            # Update averages — recalculate efficiently
            total_tokens = sum(len(e.tokens) for e in self._entries)
            self._total_docs = len(self._entries)
            self._avg_doc_length = total_tokens / max(self._total_docs, 1)

            # Update document frequencies
            for token in set(tokens):
                self._doc_freqs[token] = self._doc_freqs.get(token, 0) + 1

        logger.info(
            "BM25 index updated",
            total_docs=self._total_docs,
            new_chunks=len(chunks),
        )

    # ── Retrieval ──────────────────────────────

    async def retrieve(
        self,
        query: str,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[RetrievalCandidate]:
        """Retrieve top-k results via BM25 ranking.

        Args:
            query: Search query text.
            top_k: Number of results to return.
            filters: Optional metadata filters applied after scoring.
            **kwargs: Additional parameters.

        Returns:
            List of RetrievalCandidate ordered by BM25 score (descending).

        Raises:
            BM25IndexError: If the index has not been built.
        """
        if not self._index_built:
            raise BM25IndexError("BM25 index not built. Call build_index() first.")

        with RetrievalTimer("bm25.retrieve", tags={"top_k": str(top_k)}):
            try:
                query_tokens = self._tokenize(query)
                if not query_tokens:
                    return []

                # Score all documents
                scores: list[tuple[float, BM25IndexEntry]] = []
                for entry in self._entries:
                    score = self._bm25_score(query_tokens, entry.tokens)
                    if score > 0:
                        scores.append((score, entry))

                # Sort by score descending
                scores.sort(key=lambda x: x[0], reverse=True)

                # Apply filters if specified
                filtered = self._apply_filters(scores, filters) if filters else scores

                # Return top-k
                candidates = []
                for score, entry in filtered[:top_k]:
                    candidates.append(RetrievalCandidate(
                        chunk_id=entry.chunk_id,
                        document_id=entry.document_id,
                        text=entry.text,
                        score=score,
                        page_number=entry.page_number,
                        section_title=entry.section_title,
                        chunk_index=entry.chunk_index,
                        language=entry.language,
                        metadata=entry.metadata,
                        retrieval_source="bm25",
                    ))

                logger.debug(
                    "BM25 retrieval complete",
                    query_preview=query[:50],
                    candidates=len(candidates),
                    total_scored=len(scores),
                )
                return candidates

            except Exception as e:
                raise RetrievalError(f"BM25 retrieval failed: {e}")

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
        return "bm25"

    async def health_check(self) -> bool:
        """Check if the BM25 index is built and operational."""
        return self._index_built

    @property
    def index_size(self) -> int:
        """Get the number of documents in the index."""
        return self._total_docs

    @property
    def is_index_built(self) -> bool:
        """Check if the index has been built."""
        return self._index_built

    # ── BM25 scoring ───────────────────────────

    def _bm25_score(self, query_tokens: list[str], doc_tokens: list[str]) -> float:
        """Compute BM25 score for a query against a document.

        Args:
            query_tokens: Tokenized query.
            doc_tokens: Tokenized document.

        Returns:
            BM25 relevance score.
        """
        if not doc_tokens or not query_tokens:
            return 0.0

        doc_len = len(doc_tokens)
        doc_counter = Counter(doc_tokens)
        score = 0.0

        for token in set(query_tokens):
            if token not in self._doc_freqs:
                continue

            tf = doc_counter.get(token, 0)
            if tf == 0:
                continue

            df = self._doc_freqs[token]
            idf = math.log(1 + (self._total_docs - df + 0.5) / (df + 0.5))

            numerator = tf * (self._k1 + 1)
            denominator = tf + self._k1 * (1 - self._b + self._b * (doc_len / max(self._avg_doc_length, 1)))
            score += idf * (numerator / denominator)

        return score

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Tokenize text into lowercase tokens.

        Splits on non-alphanumeric characters and filters out
        short tokens (length < 2).

        Args:
            text: Input text.

        Returns:
            List of tokens.
        """
        tokens = re.findall(r"\b[a-z0-9]+\b", text.lower())
        return [t for t in tokens if len(t) > 1]

    @staticmethod
    def _apply_filters(
        scores: list[tuple[float, BM25IndexEntry]],
        filters: dict[str, Any],
    ) -> list[tuple[float, BM25IndexEntry]]:
        """Apply metadata filters to scored results.

        Args:
            scores: List of (score, entry) tuples.
            filters: Dict of field -> value to filter by.

        Returns:
            Filtered list of (score, entry) tuples.
        """
        if not filters:
            return scores

        filtered = []
        for score, entry in scores:
            match = True
            for key, value in filters.items():
                if key == "document_id":
                    if entry.document_id != value:
                        match = False
                elif key == "language":
                    if entry.language != value:
                        match = False
                elif key == "metadata" and isinstance(value, dict):
                    for mk, mv in value.items():
                        if entry.metadata.get(mk) != mv:
                            match = False
                            break
                elif key in entry.metadata:
                    if entry.metadata[key] != value:
                        match = False
            if match:
                filtered.append((score, entry))

        return filtered
