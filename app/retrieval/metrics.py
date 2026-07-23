"""Retrieval metrics — counters, timers, and histograms for the retrieval pipeline.

Designed to be pluggable into Prometheus/OpenTelemetry later.
Currently uses the centralized metrics system from app.core.metrics.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from app.core.metrics import get_metrics


@dataclass
class RetrievalTimer:
    """Context manager for timing retrieval operations."""

    name: str
    tags: dict[str, str] = field(default_factory=dict)
    _start: float = 0.0
    _elapsed_ms: float = 0.0

    def __enter__(self) -> RetrievalTimer:
        self._start = time.monotonic()
        return self

    def __exit__(self, *args: Any) -> None:
        self._elapsed_ms = (time.monotonic() - self._start) * 1000
        get_metrics().timing(self.name, self._elapsed_ms, tags=self.tags)

    @property
    def elapsed_ms(self) -> float:
        return self._elapsed_ms


def record_retrieval_metrics(
    method: str,
    duration_ms: float,
    total_results: int,
    rerank_ms: float | None = None,
    cache_hits: int = 0,
    dedup_removed: int = 0,
    error: str | None = None,
) -> None:
    """Record retrieval operation metrics.

    Args:
        method: Retrieval method used (dense, bm25, hybrid, parent_child).
        duration_ms: Total operation duration.
        total_results: Number of results returned.
        rerank_ms: Reranker duration if applied.
        cache_hits: Number of cache hits.
        dedup_removed: Number of duplicates removed.
        error: Error code if the operation failed.
    """
    tags = {"method": method}
    if error:
        tags["error"] = error

    get_metrics().increment("retrieval.requests", tags=tags)
    get_metrics().timing("retrieval.duration_ms", duration_ms, tags=tags)
    get_metrics().gauge("retrieval.total_results", total_results, tags=tags)

    if rerank_ms is not None:
        get_metrics().timing("retrieval.rerank_ms", rerank_ms, tags=tags)

    if cache_hits:
        get_metrics().increment("retrieval.cache_hits", tags=tags)

    if dedup_removed:
        get_metrics().gauge("retrieval.dedup_removed", dedup_removed, tags=tags)


def record_reranker_metrics(
    provider: str,
    duration_ms: float,
    candidates: int,
    error: str | None = None,
) -> None:
    """Record reranker operation metrics.

    Args:
        provider: Reranker provider name.
        duration_ms: Reranker duration.
        candidates: Number of candidates reranked.
        error: Error code if the operation failed.
    """
    tags = {"provider": provider}
    if error:
        tags["error"] = error

    get_metrics().increment("retrieval.rerank_calls", tags=tags)
    get_metrics().timing("retrieval.rerank_ms", duration_ms, tags=tags)
    get_metrics().gauge("retrieval.rerank_candidates", candidates, tags=tags)
