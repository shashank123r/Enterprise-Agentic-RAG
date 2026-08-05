"""Metrics abstraction for the ingestion pipeline.

Provides a simple counter/timer/gauge interface so the business logic
never depends on a specific metrics backend. Swap Prometheus, OpenTelemetry,
or StatsD without touching ingestion code.
"""

import time
from collections import defaultdict
from typing import Any


class MetricsBackend:
    """Abstract metrics collector. Drop-in replaceable via configure()."""

    def increment(self, metric: str, value: int = 1, tags: dict[str, str] | None = None) -> None:
        """Increment a counter."""
        ...

    def gauge(self, metric: str, value: float, tags: dict[str, str] | None = None) -> None:
        """Record a gauge value."""
        ...

    def timing(self, metric: str, value_ms: float, tags: dict[str, str] | None = None) -> None:
        """Record a timing/histogram in milliseconds."""
        ...

    def flush(self) -> None:
        """Flush any buffered metrics."""
        ...


class LoggingMetricsBackend(MetricsBackend):
    """Metrics backend that logs all metric calls via structlog.

    Used in development. Swap for PrometheusBackend in staging/production.
    """

    def __init__(self) -> None:
        from app.core.logging import get_logger

        self._logger = get_logger("metrics")
        self._counters: dict[str, int] = defaultdict(int)

    def increment(self, metric: str, value: int = 1, tags: dict[str, str] | None = None) -> None:
        self._counters[metric] += value

    def gauge(self, metric: str, value: float, tags: dict[str, str] | None = None) -> None:
        self._logger.info(metric, type="gauge", value=value, tags=tags)

    def timing(self, metric: str, value_ms: float, tags: dict[str, str] | None = None) -> None:
        self._logger.info(metric, type="timing", value_ms=value_ms, tags=tags)

    def flush(self) -> None:
        for metric, count in self._counters.items():
            self._logger.info(metric, type="counter", value=count)
        self._counters.clear()


# Global singleton — configured at startup
_metrics: MetricsBackend = LoggingMetricsBackend()


def configure_metrics(backend: MetricsBackend) -> None:
    """Replace the global metrics backend (e.g. with Prometheus during startup)."""
    global _metrics
    _metrics = backend


def get_metrics() -> MetricsBackend:
    """Return the current metrics backend."""
    return _metrics


class Timer:
    """Context manager for timing operations.

    Usage:
        with Timer("ingestion.duration", tags={"doc_type": "pdf"}) as timer:
            await process_document(...)
    """

    def __init__(self, metric: str, tags: dict[str, str] | None = None) -> None:
        self.metric = metric
        self.tags = tags or {}
        self._start: float = 0.0

    async def __aenter__(self) -> "Timer":
        self._start = time.monotonic()
        return self

    async def __aexit__(self, *args: Any) -> None:
        elapsed_ms = (time.monotonic() - self._start) * 1000
        get_metrics().timing(self.metric, elapsed_ms, tags=self.tags)


# ── Convenience helpers ────────────────────────────────────


def incr(metric: str, value: int = 1, tags: dict[str, str] | None = None) -> None:
    """Increment a counter metric."""
    get_metrics().increment(metric, value, tags)


def record_timing(metric: str, value_ms: float, tags: dict[str, str] | None = None) -> None:
    """Record a timing value in milliseconds."""
    get_metrics().timing(metric, value_ms, tags)


def record_gauge(metric: str, value: float, tags: dict[str, str] | None = None) -> None:
    """Record a gauge value."""
    get_metrics().gauge(metric, value, tags)
