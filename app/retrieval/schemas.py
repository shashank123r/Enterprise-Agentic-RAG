"""Pydantic schemas for the Enterprise Retrieval Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# ── API Request / Response Schemas ────────────


class RetrievalRequest(BaseModel):
    """Request payload for a retrieval query."""

    query: str = Field(..., min_length=1, max_length=8192, description="Search query text")
    collection_name: str = Field("documents", description="Milvus collection to search")
    top_k: int = Field(10, ge=1, le=100, description="Number of results to return")
    method: str = Field("hybrid", description="Retrieval method: dense, bm25, hybrid, parent_child")
    filters: dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata filters (e.g. {'language': 'en', 'document_id': '...'})",
    )
    rerank: bool = Field(True, description="Whether to apply reranking")
    rerank_top_k: int = Field(20, ge=1, le=200, description="Number of candidates to rerank")
    hybrid_alpha: float = Field(
        0.5, ge=0.0, le=1.0, description="Dense weight for hybrid search (0=BM25, 1=dense)"
    )
    min_score: float | None = Field(None, ge=0.0, description="Minimum similarity score threshold")
    query_rewrite: bool = Field(False, description="Apply query rewriting before search")
    query_expansion: bool = Field(False, description="Apply query expansion (synonym expansion)")
    max_context_tokens: int | None = Field(None, description="Maximum tokens for context window")


class RetrievedChunk(BaseModel):
    """A single retrieved chunk with metadata and score."""

    chunk_id: str = Field(..., description="Chunk UUID")
    document_id: str = Field(..., description="Document UUID")
    text: str = Field(..., description="Chunk text content")
    score: float = Field(0.0, description="Similarity/relevance score")
    rerank_score: float | None = Field(None, description="Reranker score if reranked")
    page_number: int | None = Field(None, description="Source page number")
    section_title: str | None = Field(None, description="Section heading")
    chunk_index: int = Field(0, description="Position in document")
    language: str | None = Field(None, description="Detected language")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Rich metadata")
    retrieval_source: str = Field("dense", description="Which retriever found this chunk")

    model_config = {"from_attributes": True}


class Citation(BaseModel):
    """Citation for a retrieved chunk.

    Every citation includes:
    - document_id
    - document_title (from metadata)
    - chunk_id
    - page number
    - section title
    - retrieval score
    - retrieval method (dense, bm25, hybrid, reranked)
    - source (document filename/URL)
    """

    chunk_id: str = Field(..., description="Chunk UUID")
    document_id: str = Field(..., description="Document UUID")
    document_title: str = Field("", description="Document title from metadata")
    source: str = Field("", description="Source filename or URL")
    retrieval_method: str = Field("dense", description="Retrieval method used")
    text_preview: str = Field(..., max_length=200, description="First 200 chars of chunk text")
    page_number: int | None = Field(None, description="Source page number")
    section_title: str | None = Field(None, description="Section heading")
    score: float = Field(0.0, description="Retrieval score")
    rerank_score: float | None = Field(None, description="Reranker score")


class RetrievalMetrics(BaseModel):
    """Metrics for a retrieval operation."""

    total_duration_ms: float = 0.0
    vector_search_ms: float = 0.0
    bm25_search_ms: float | None = None
    hybrid_fusion_ms: float | None = None
    rerank_ms: float | None = None
    query_rewrite_ms: float | None = None
    context_build_ms: float | None = None
    total_chunks_retrieved: int = 0
    chunks_after_rerank: int | None = None
    dedup_removed: int = 0
    method: str = "hybrid"


class RetrievalResult(BaseModel):
    """Complete retrieval result with chunks, citations, and metrics."""

    query: str = Field(..., description="Original query (or rewritten if rewrite was applied)")
    rewritten_query: str | None = Field(None, description="Rewritten query if rewrite was applied")
    chunks: list[RetrievedChunk] = Field(default_factory=list, description="Retrieved chunks")
    citations: list[Citation] = Field(default_factory=list, description="Generated citations")
    context: str | None = Field(None, description="Assembled context window")
    metrics: RetrievalMetrics = Field(
        default_factory=RetrievalMetrics, description="Performance metrics"
    )
    method: str = Field("hybrid", description="Retrieval method used")
    total_results: int = 0

    model_config = {"from_attributes": True}


# ── Internal Dataclasses ─────────────────────


@dataclass
class RetrievalCandidate:
    """Internal representation of a retrieved chunk before final formatting."""

    chunk_id: str
    document_id: str
    text: str
    score: float
    rerank_score: float | None = None
    page_number: int | None = None
    section_title: str | None = None
    chunk_index: int = 0
    language: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    retrieval_source: str = "dense"


@dataclass
class BM25IndexEntry:
    """An entry in the BM25 inverted index."""

    chunk_id: str
    document_id: str
    text: str
    tokens: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)
    page_number: int | None = None
    section_title: str | None = None
    chunk_index: int = 0
    language: str | None = None
    score: float = 0.0
    retrieval_source: str = "bm25"
