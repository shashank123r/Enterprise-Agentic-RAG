"""Pydantic schemas for the Enterprise RAG Orchestrator."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RAGRequest(BaseModel):
    """Request payload for a RAG chat interaction."""

    question: str = Field(..., min_length=1, max_length=16384, description="User question")
    collection_name: str = Field("documents", description="Milvus collection to search")
    top_k: int = Field(10, ge=1, le=50, description="Number of chunks to retrieve")
    retrieval_method: str = Field("hybrid", description="Retrieval method: dense, bm25, hybrid, parent_child")
    rerank: bool = Field(True, description="Whether to apply reranking")
    query_rewrite: bool = Field(True, description="Apply query rewriting before search")
    filters: dict[str, Any] = Field(default_factory=dict, description="Metadata filters")
    max_context_tokens: int | None = Field(4096, ge=256, le=32768, description="Max tokens for context window")
    max_response_tokens: int | None = Field(1024, ge=64, le=16384, description="Max tokens in response")
    temperature: float | None = Field(0.1, ge=0.0, le=2.0, description="LLM temperature")
    stream: bool = Field(True, description="Whether to stream the response")
    conversation_history: list[dict[str, str]] | None = Field(
        None,
        description="Previous messages: [{\"role\": \"user\"|\"assistant\", \"content\": \"...\"}]",
    )


class RAGChunk(BaseModel):
    """A single chunk used in the RAG response."""

    chunk_id: str = Field(..., description="Chunk UUID")
    document_id: str = Field(..., description="Document UUID")
    document_title: str = Field("", description="Document title")
    text_preview: str = Field(..., max_length=300, description="First 300 chars of chunk")
    page_number: int | None = Field(None, description="Source page number")
    section_title: str | None = Field(None, description="Section heading")
    score: float = Field(0.0, description="Retrieval score")
    retrieval_method: str = Field("dense", description="Retrieval method")


class CitationInfo(BaseModel):
    """Citation reference within the generated answer."""

    index: int = Field(..., ge=1, description="Citation number in the answer")
    chunk_id: str = Field(..., description="Referenced chunk UUID")
    document_id: str = Field(..., description="Document UUID")
    document_title: str = Field("", description="Document title")
    source: str = Field("", description="Source filename or URL")
    retrieval_method: str = Field("dense", description="Retrieval method used")
    page_number: int | None = Field(None, description="Source page number")
    section_title: str | None = Field(None, description="Section heading")
    text_preview: str = Field(..., max_length=300, description="Supporting text from chunk")


class RAGResponse(BaseModel):
    """Complete RAG response with answer, citations, and metrics."""

    answer: str = Field(..., description="Generated answer")
    citations: list[CitationInfo] = Field(default_factory=list, description="Inline citations")
    chunks: list[RAGChunk] = Field(default_factory=list, description="Source chunks used")
    grounding_valid: bool = Field(True, description="Whether answer passed grounding check")
    grounding_issues: list[str] = Field(default_factory=list, description="Any grounding failures")
    llm_model: str = Field("", description="LLM model used")
    total_duration_ms: float = 0.0
    retrieval_duration_ms: float = 0.0
    llm_duration_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ValidateRequest(BaseModel):
    """Request payload for answer validation."""

    question: str = Field(..., min_length=1, description="Original question")
    answer: str = Field(..., min_length=1, description="Generated answer to validate")
    chunks: list[RAGChunk] = Field(..., description="Source chunks used")


class ValidateResponse(BaseModel):
    """Response from answer validation."""

    grounding_valid: bool = Field(True, description="Whether answer is properly grounded")
    issues: list[str] = Field(default_factory=list, description="Any grounding issues found")
    unsupported_statements: list[str] = Field(default_factory=list, description="Specific unsupported claims")
    suggested_fixes: list[str] = Field(default_factory=list, description="Suggested corrections")
