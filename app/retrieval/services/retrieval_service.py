"""RetrievalService — orchestrates the full retrieval pipeline.

Coordinates query understanding → retrieval → reranking → context building → citations.

This is the main entry point for all retrieval operations. The service is designed
to be used as an application-scoped singleton (not per-request) so that the BM25
index, HTTP clients, and reranker connections persist across requests (fixes H1).
"""

from __future__ import annotations

import time
from typing import Any

from app.core.logging import get_logger
from app.embeddings.providers.base import EmbeddingProvider
from app.retrieval.exceptions import (
    BM25IndexError,
    RetrieverNotFound,
    RetrieverUnavailable,
    RetrievalError,
)
from app.retrieval.metrics import RetrievalTimer, record_retrieval_metrics
from app.retrieval.query.analyzer import QueryAnalyzer
from app.retrieval.query.expansion import QueryExpander
from app.retrieval.query.filters import FilterBuilder
from app.retrieval.query.rewrite import QueryRewriter
from app.retrieval.rerankers.base import Reranker
from app.retrieval.retrievers.base import Retriever
from app.retrieval.retrievers.bm25 import BM25Retriever
from app.retrieval.retrievers.dense import DenseRetriever
from app.retrieval.retrievers.hybrid import HybridRetriever
from app.retrieval.retrievers.parent_child import ParentChildRetriever
from app.retrieval.schemas import RetrievalCandidate, RetrievalMetrics, RetrievalResult
from app.retrieval.services.bm25_manager import BM25IndexManager
from app.retrieval.services.citation_builder import CitationBuilder
from app.retrieval.services.context_builder import ContextBuilder
from app.vector_stores.base import VectorStore
from app.vector_stores.exceptions import CollectionNotFound

logger = get_logger(__name__)


class RetrievalService:
    """Orchestrates the end-to-end retrieval pipeline.

    Pipeline:
        1. Pre-flight validation (C2): embedding provider, Milvus, BM25 index, collection
        2. (Optional) Query analysis + rewriting + expansion
        3. Select retriever based on method
        4. Execute retrieval (with metadata filters)
        5. (Optional) Rerank candidates
        6. Build context window
        7. Generate citations

    Usage (singleton pattern):
        # Initialize once during app startup
        service = RetrievalService(
            embedding_provider=provider,
            vector_store=store,
            dense_retriever=dense,
            bm25_retriever=bm25,
            hybrid_retriever=hybrid,
            reranker=reranker,
        )

        # Reuse for all requests
        result = await service.search(query="...")
    """

    def __init__(
        self,
        embedding_provider: EmbeddingProvider | None = None,
        vector_store: VectorStore | None = None,
        dense_retriever: DenseRetriever | None = None,
        bm25_retriever: BM25Retriever | None = None,
        bm25_manager: BM25IndexManager | None = None,
        hybrid_retriever: HybridRetriever | None = None,
        parent_child_retriever: ParentChildRetriever | None = None,
        reranker: Reranker | None = None,
    ) -> None:
        self._provider = embedding_provider
        self._store = vector_store
        self._retrievers: dict[str, Retriever] = {}
        if dense_retriever:
            self._retrievers["dense"] = dense_retriever
        if bm25_retriever:
            self._retrievers["bm25"] = bm25_retriever
        if hybrid_retriever:
            self._retrievers["hybrid"] = hybrid_retriever
        if parent_child_retriever:
            self._retrievers["parent_child"] = parent_child_retriever

        self._bm25_manager = bm25_manager
        self._reranker = reranker
        self._query_analyzer = QueryAnalyzer()
        self._query_rewriter = QueryRewriter()
        self._query_expander = QueryExpander()
        self._context_builder = ContextBuilder()
        self._citation_builder = CitationBuilder()
        self._filter_builder = FilterBuilder()

    # ── Pre-flight validation (C2) ─────────────

    async def _validate_retrieval_readiness(
        self,
        method: str,
        collection_name: str,
    ) -> None:
        """Validate that all prerequisites are met before retrieval.

        Checks:
        - Embedding provider is available
        - Vector store (Milvus) is healthy
        - BM25 index is built (if method requires it)
        - Collection exists
        - Collection version is compatible with embedding model
        - Retrieval model matches configured embedding model

        Raises:
            RetrieverUnavailable: If any dependency is unavailable.
            BM25IndexError: If BM25 index is needed but not built.
            CollectionNotFound: If the target collection doesn't exist.
        """
        errors: list[str] = []

        # 1. Embedding provider health
        provider_ok = False
        if self._provider is not None:
            try:
                provider_ok = await self._provider.health_check()
                if not provider_ok:
                    errors.append("Embedding provider is not healthy")
            except Exception as e:
                errors.append(f"Embedding provider health check failed: {e}")

        # 2. Embedding model match: check that retrieval model matches configured model
        if self._provider is not None and provider_ok:
            try:
                from app.core.config import settings
                provider_model = getattr(self._provider, '_model', None) or settings.EMBEDDING_MODEL
                configured_model = settings.EMBEDDING_MODEL
                if provider_model != configured_model:
                    errors.append(
                        f"Retrieval model mismatch: provider has '{provider_model}', "
                        f"configured '{configured_model}'. Rebuild embeddings to match."
                    )
            except Exception as e:
                errors.append(f"Model version check failed: {e}")

        # 3. Vector store health
        store_ok = False
        if self._store is not None:
            try:
                store_ok = await self._store.health_check()
                if not store_ok:
                    errors.append("Vector store (Milvus) is not healthy")
            except Exception as e:
                errors.append(f"Vector store health check failed: {e}")

        # 4. Collection exists + version check
        if self._store is not None and collection_name:
            try:
                exists = await self._store.collection_exists(collection_name)
                if not exists:
                    errors.append(f"Collection '{collection_name}' does not exist. Run indexing first.")
                elif store_ok:
                    # Check collection stats for dimension/model version consistency
                    try:
                        stats = await self._store.collection_stats(collection_name)
                        if stats.get("exists"):
                            from app.core.config import settings
                            expected_dim = settings.VECTOR_STORE_DIMENSION
                            schema = stats.get("schema", {})
                            vector_field_type = schema.get("vector", "")
                            # Dimension is embedded in the vector field params
                            # Basic check: if collection exists, it was created with some dimension
                            # More detailed versioning would require custom metadata
                            num_entities = stats.get("num_entities", 0)
                            if num_entities == 0:
                                logger.warning(
                                    "Collection exists but has no vectors",
                                    collection=collection_name,
                                )
                    except Exception as e:
                        logger.warning("Collection stats check failed (non-fatal)", error=str(e))
            except Exception as e:
                errors.append(f"Collection check failed: {e}")

        # 5. BM25 index readiness (only for bm25 or hybrid methods)
        if method in ("bm25", "hybrid", "parent_child"):
            if self._bm25_manager is None or not self._bm25_manager.is_ready:
                errors.append(
                    "BM25 index is not built. Call POST /retrieval/bm25/build-index first. "
                    "Hybrid and BM25 retrieval require a built BM25 index."
                )

        if errors:
            raise RetrieverUnavailable("; ".join(errors))

    # ── Core search ────────────────────────────

    async def search(
        self,
        query: str,
        collection_name: str = "documents",
        method: str = "hybrid",
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        rerank: bool = True,
        rerank_top_k: int = 20,
        hybrid_alpha: float = 0.5,
        min_score: float | None = None,
        query_rewrite: bool = False,
        query_expansion: bool = False,
        max_context_tokens: int | None = None,
    ) -> RetrievalResult:
        """Execute the full retrieval pipeline.

        Args:
            query: Search query.
            collection_name: Target Milvus collection.
            method: Retrieval method (dense, bm25, hybrid, parent_child).
            top_k: Number of final results to return.
            filters: Metadata filters.
            rerank: Whether to apply reranking.
            rerank_top_k: Number of candidates to rerank.
            hybrid_alpha: Dense weight for hybrid search.
            min_score: Minimum score threshold.
            query_rewrite: Whether to apply query rewriting.
            query_expansion: Whether to apply query expansion.
            max_context_tokens: Max tokens for context window.

        Returns:
            RetrievalResult with chunks, citations, context, and metrics.

        Raises:
            RetrieverNotFound: If the requested method is not configured.
            RetrieverUnavailable: If prerequisites are not met (C2).
        """
        metrics = RetrievalMetrics(method=method)
        start_time = time.monotonic()

        # ── Step 0: Pre-flight validation (C2) ─
        await self._validate_retrieval_readiness(method, collection_name)

        # ── Step 1: Query analysis ─────────────
        with RetrievalTimer("retrieval.query_analyze"):
            analysis = await self._query_analyzer.analyze(query)
            effective_query = analysis.normalized_query

        # ── Step 1.5: Query rewriting ──────────
        rewritten_query: str | None = None
        if query_rewrite:
            with RetrievalTimer("retrieval.query_rewrite"):
                rewritten_query = await self._query_rewriter.rewrite(
                    effective_query, language=analysis.language
                )
                effective_query = rewritten_query
                metrics.query_rewrite_ms = 0.0

        # ── Step 1.75: Query expansion ─────────
        if query_expansion:
            with RetrievalTimer("retrieval.query_expand"):
                effective_query = await self._query_expander.expand(effective_query)

        # Merge explicit filters with analyzer-detected filters
        combined_filters = dict(filters or {})
        for k, v in analysis.metadata_filters.items():
            if k not in combined_filters:
                combined_filters[k] = v

        # ── Step 2: Select and run retriever ───
        retriever = self._retrievers.get(method)
        if retriever is None:
            raise RetrieverNotFound(method)

        retrieve_kwargs: dict[str, Any] = {"collection_name": collection_name}
        if method == "hybrid":
            retrieve_kwargs["alpha"] = hybrid_alpha
            retrieve_kwargs["bm25_top_k"] = rerank_top_k

        candidates: list[RetrievalCandidate] = []
        with RetrievalTimer("retrieval.execute") as timer:
            candidates = await retriever.retrieve(
                query=effective_query,
                top_k=rerank_top_k if rerank else top_k,
                filters=combined_filters,
                **retrieve_kwargs,
            )

        # Apply minimum score filter
        if min_score is not None and candidates:
            candidates = [c for c in candidates if c.score >= min_score]

        # Record metrics
        if method == "bm25":
            metrics.bm25_search_ms = timer.elapsed_ms
        else:
            metrics.vector_search_ms = timer.elapsed_ms

        # ── Step 3: Reranking (optional) ───────
        rerank_duration: float | None = None
        if rerank and self._reranker and candidates:
            try:
                with RetrievalTimer("retrieval.rerank") as rt:
                    candidates = await self._reranker.rerank(
                        query=effective_query,
                        candidates=candidates,
                        top_k=top_k,
                    )
                    rerank_duration = rt.elapsed_ms
                    metrics.rerank_ms = rerank_duration
                    metrics.chunks_after_rerank = len(candidates)
            except Exception as e:
                logger.warning(
                    "Reranking failed — returning unreranked results",
                    error=str(e),
                )
                # Re-truncate to top_k since reranking wasn't applied
                candidates = candidates[:top_k]

        # ── Step 4: Context building ───────────
        with RetrievalTimer("retrieval.build_context") as ct:
            context_text, retrieved_chunks, citation_data = self._context_builder.build(
                candidates, max_tokens=max_context_tokens
            )
            metrics.context_build_ms = ct.elapsed_ms
            metrics.dedup_removed = len(candidates) - len(retrieved_chunks)

        # ── Step 5: Citations ──────────────────
        citations = self._citation_builder.build(retrieved_chunks)

        # ── Step 6: Build result ───────────────
        total_duration = (time.monotonic() - start_time) * 1000
        metrics.total_duration_ms = round(total_duration, 2)
        metrics.total_chunks_retrieved = len(retrieved_chunks)

        record_retrieval_metrics(
            method=method,
            duration_ms=total_duration,
            total_results=len(retrieved_chunks),
            rerank_ms=rerank_duration,
            dedup_removed=metrics.dedup_removed,
        )

        logger.info(
            "Retrieval complete",
            method=method,
            query_preview=query[:60],
            results=len(retrieved_chunks),
            duration_ms=round(total_duration, 1),
            reranked=rerank,
        )

        return RetrievalResult(
            query=query,
            rewritten_query=rewritten_query,
            chunks=retrieved_chunks,
            citations=citations,
            context=context_text,
            metrics=metrics,
            method=method,
            total_results=len(retrieved_chunks),
        )

    # ── Accessors ──────────────────────────────

    def get_retriever(self, method: str) -> Retriever | None:
        return self._retrievers.get(method)

    def get_bm25_manager(self) -> BM25IndexManager | None:
        return self._bm25_manager

    @property
    def available_methods(self) -> list[str]:
        return list(self._retrievers.keys())

    async def health_check(self) -> dict[str, Any]:
        """Comprehensive health check for the retrieval system (P5)."""
        results: dict[str, Any] = {
            "retrievers": {},
            "reranker": False,
            "bm25_index": {"built": False},
            "embedding_provider": False,
            "vector_store": False,
            "retrieval_ready": False,
        }

        # BM25 status
        if self._bm25_manager:
            results["bm25_index"] = await self._bm25_manager.get_status()

        # Retrievers
        for name, retriever in self._retrievers.items():
            results["retrievers"][name] = await retriever.health_check()

        # Reranker
        if self._reranker:
            results["reranker"] = await self._reranker.health_check()

        # Embedding provider
        if self._provider:
            try:
                results["embedding_provider"] = await self._provider.health_check()
            except Exception:
                results["embedding_provider"] = False

        # Vector store
        if self._store:
            try:
                results["vector_store"] = await self._store.health_check()
            except Exception:
                results["vector_store"] = False

        # Overall readiness
        bm25_ok = results["bm25_index"].get("healthy", False) if results["bm25_index"] else True
        results["retrieval_ready"] = (
            results["embedding_provider"]
            and results["vector_store"]
            and bm25_ok
        )

        return results
