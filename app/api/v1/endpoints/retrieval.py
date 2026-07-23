"""Retrieval API endpoints — search, BM25 index lifecycle, and health.

The RetrievalService is used as an application-scoped singleton (H1).
BM25 lifecycle endpoints allow building/rebuilding the keyword index (C1).
Health endpoint provides comprehensive system status (P5).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.embeddings.providers.base import EmbeddingProvider
from app.embeddings.providers.factory import get_embedding_provider
from app.retrieval.exceptions import (
    BM25IndexError,
    RetrieverNotFound,
    RetrieverUnavailable,
)
from app.retrieval.schemas import RetrievalRequest, RetrievalResult
from app.retrieval.services.retrieval_service import RetrievalService
from app.vector_stores.base import VectorStore
from app.vector_stores.factory import get_vector_store

router = APIRouter(prefix="/retrieval", tags=["retrieval"])

# ── Application-scoped singleton (H1) ─────────
# Initialized on first use, reused for all requests.
_retrieval_service: RetrievalService | None = None


async def get_retrieval_service(
    provider: EmbeddingProvider = Depends(get_embedding_provider),
    store: VectorStore = Depends(get_vector_store),
) -> RetrievalService:
    """Get or create the application-scoped RetrievalService singleton.

    The service, retrievers, BM25 index, and reranker HTTP clients
    persist across requests — no per-request recreation (fixes H1).
    """
    global _retrieval_service
    if _retrieval_service is None:
        from app.retrieval.retrievers.dense import DenseRetriever
        from app.retrieval.retrievers.bm25 import BM25Retriever
        from app.retrieval.retrievers.hybrid import HybridRetriever
        from app.retrieval.retrievers.parent_child import ParentChildRetriever
        from app.retrieval.rerankers.cross_encoder import CrossEncoderReranker
        from app.retrieval.services.bm25_manager import BM25IndexManager

        bm25 = BM25Retriever()
        bm25_manager = BM25IndexManager(bm25)
        dense = DenseRetriever(embedding_provider=provider, vector_store=store)
        hybrid = HybridRetriever(dense_retriever=dense, bm25_retriever=bm25)
        parent_child = ParentChildRetriever(base_retriever=hybrid)
        reranker = CrossEncoderReranker()

        _retrieval_service = RetrievalService(
            embedding_provider=provider,
            vector_store=store,
            dense_retriever=dense,
            bm25_retriever=bm25,
            bm25_manager=bm25_manager,
            hybrid_retriever=hybrid,
            parent_child_retriever=parent_child,
            reranker=reranker,
        )
    return _retrieval_service


# ── Search endpoints ─────────────────────────


@router.post("/search", summary="Execute a retrieval search")
async def search(
    request: RetrievalRequest,
    service: RetrievalService = Depends(get_retrieval_service),
) -> RetrievalResult:
    """Execute the full retrieval pipeline.

    Supports dense, BM25, hybrid (RRF fusion), and parent-child retrieval
    methods. Optionally applies reranking, query rewriting, and expansion.

    Returns chunks with scores, citations, and a built context window.
    """
    try:
        result = await service.search(
            query=request.query,
            collection_name=request.collection_name,
            method=request.method,
            top_k=request.top_k,
            filters=request.filters,
            rerank=request.rerank,
            rerank_top_k=request.rerank_top_k,
            hybrid_alpha=request.hybrid_alpha,
            min_score=request.min_score,
            query_rewrite=request.query_rewrite,
            query_expansion=request.query_expansion,
            max_context_tokens=request.max_context_tokens,
        )
        return result
    except (RetrieverNotFound, RetrieverUnavailable, BM25IndexError) as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))


@router.post("/search/dense", summary="Dense vector search")
async def search_dense(
    query: str = Query(..., min_length=1, max_length=8192),
    top_k: int = Query(10, ge=1, le=100),
    collection_name: str = Query("documents"),
    service: RetrievalService = Depends(get_retrieval_service),
) -> RetrievalResult:
    """Quick dense vector search endpoint."""
    return await service.search(
        query=query,
        collection_name=collection_name,
        method="dense",
        top_k=top_k,
        rerank=False,
    )


@router.post("/search/hybrid", summary="Hybrid dense+BM25 search with RRF")
async def search_hybrid(
    query: str = Query(..., min_length=1, max_length=8192),
    top_k: int = Query(10, ge=1, le=100),
    alpha: float = Query(0.5, ge=0.0, le=1.0),
    collection_name: str = Query("documents"),
    service: RetrievalService = Depends(get_retrieval_service),
) -> RetrievalResult:
    """Hybrid search combining dense vectors and BM25 with RRF fusion."""
    return await service.search(
        query=query,
        collection_name=collection_name,
        method="hybrid",
        top_k=top_k,
        hybrid_alpha=alpha,
        rerank=False,
    )


# ── BM25 Index Lifecycle (C1) ──────────────────


@router.post("/bm25/build-index", summary="Build BM25 index from ingestion repository")
async def bm25_build_index(
    db: AsyncSession = Depends(get_db),
    service: RetrievalService = Depends(get_retrieval_service),
) -> dict[str, Any]:
    """Build the BM25 inverted index from ingested document chunks.

    Loads all chunks from DocumentChunkRepository and builds the
    BM25 keyword index. Required before hybrid or BM25 retrieval.
    """
    manager = service.get_bm25_manager()
    if manager is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="BM25 manager not configured",
        )
    try:
        stats = await manager.build_from_repository(db)
        return {"status": "built", **stats}
    except BM25IndexError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/bm25/rebuild", summary="Rebuild BM25 index from scratch")
async def bm25_rebuild(
    db: AsyncSession = Depends(get_db),
    service: RetrievalService = Depends(get_retrieval_service),
) -> dict[str, Any]:
    """Rebuild the BM25 index from scratch.

    Clears the existing index and rebuilds from the ingestion repository.
    """
    manager = service.get_bm25_manager()
    if manager is None:
        raise HTTPException(status_code=500, detail="BM25 manager not configured")
    try:
        stats = await manager.rebuild(db)
        return {"status": "rebuilt", **stats}
    except BM25IndexError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bm25/status", summary="Get BM25 index status")
async def bm25_status(
    service: RetrievalService = Depends(get_retrieval_service),
) -> dict[str, Any]:
    """Get the current status of the BM25 inverted index."""
    manager = service.get_bm25_manager()
    if manager is None:
        return {"index_built": False, "reason": "BM25 manager not configured"}
    return await manager.get_status()


@router.delete("/bm25", summary="Clear BM25 index")
async def bm25_clear(
    service: RetrievalService = Depends(get_retrieval_service),
) -> dict[str, Any]:
    """Clear the BM25 index entirely."""
    manager = service.get_bm25_manager()
    if manager is not None:
        await manager.clear()
    return {"status": "cleared"}


# ── Metadata ──────────────────────────────────


@router.get("/methods", summary="List available retrieval methods")
async def available_methods(
    service: RetrievalService = Depends(get_retrieval_service),
) -> dict[str, Any]:
    """Get a list of supported retrieval methods and BM25 status."""
    bm25_status = False
    manager = service.get_bm25_manager()
    if manager:
        status = await manager.get_status()
        bm25_status = status.get("healthy", False)

    return {
        "methods": service.available_methods,
        "default": "hybrid",
        "bm25_index_built": bm25_status,
        "note": "Hybrid and BM25 methods require building BM25 index via /bm25/build-index",
    }


# ── Health (P5) ────────────────────────────────


@router.get("/health", summary="Retrieval system health check")
async def health(
    service: RetrievalService = Depends(get_retrieval_service),
) -> dict[str, Any]:
    """Comprehensive health check for the retrieval system.

    Returns status of:
    - BM25 index
    - Milvus (vector store)
    - Embedding provider
    - Reranker
    - Overall retrieval readiness
    """
    return await service.health_check()
