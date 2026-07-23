"""RAG observability — tracks LLM latency, token usage, grounding, and citations."""

from __future__ import annotations

from typing import Any

from app.core.metrics import get_metrics


def record_rag_metrics(
    llm_model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_duration_ms: float,
    llm_duration_ms: float,
    retrieval_duration_ms: float,
    citation_count: int,
    grounding_valid: bool,
    streamed: bool = False,
    error: str | None = None,
) -> None:
    """Record RAG operation metrics.

    Args:
        llm_model: Model name used.
        prompt_tokens: Input token count.
        completion_tokens: Output token count.
        total_duration_ms: End-to-end duration.
        llm_duration_ms: LLM call duration.
        retrieval_duration_ms: Retrieval duration.
        citation_count: Number of citations in response.
        grounding_valid: Whether grounding check passed.
        streamed: Whether response was streamed.
        error: Error code if the operation failed.
    """
    tags = {"model": llm_model}
    if error:
        tags["error"] = error

    get_metrics().increment("rag.requests", tags=tags)
    get_metrics().timing("rag.total_duration_ms", total_duration_ms, tags=tags)
    get_metrics().timing("rag.llm_duration_ms", llm_duration_ms, tags=tags)
    get_metrics().timing("rag.retrieval_duration_ms", retrieval_duration_ms, tags=tags)
    get_metrics().gauge("rag.prompt_tokens", prompt_tokens, tags=tags)
    get_metrics().gauge("rag.completion_tokens", completion_tokens, tags=tags)
    get_metrics().gauge("rag.total_tokens", prompt_tokens + completion_tokens, tags=tags)
    get_metrics().gauge("rag.citation_count", citation_count, tags=tags)

    if not grounding_valid:
        get_metrics().increment("rag.grounding_failures", tags=tags)

    if streamed:
        get_metrics().increment("rag.streamed_responses", tags=tags)
