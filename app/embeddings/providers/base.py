"""Abstract embedding provider interface.

All embedding operations go through this interface. Business logic
depends only on EmbeddingProvider — never on a concrete implementation.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EmbeddingResult:
    """Result of a single embedding operation."""

    vector: list[float]
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    token_count: int = 0
    model: str = ""


@dataclass
class BatchEmbeddingResult:
    """Result of a batch embedding operation."""

    vectors: list[list[float]]
    texts: list[str]
    metadata: list[dict[str, Any]] = field(default_factory=list)
    token_counts: list[int] = field(default_factory=list)
    model: str = ""
    failed_indices: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class EmbeddingProviderInfo:
    """Metadata about the embedding provider and model."""

    provider_name: str
    model_name: str
    model_version: str = ""
    dimension: int = 0
    max_input_tokens: int = 512
    supported_languages: list[str] = field(default_factory=lambda: ["en"])
    requires_api_key: bool = True


class EmbeddingProvider(ABC):
    """Abstract embedding provider.

    All methods are async. Implementations must handle:
    - Network failures (retry + convert to EmbeddingError)
    - Rate limiting (backoff + retry)
    - Timeouts
    - Malformed responses
    - Partial batch failures
    """

    # ── Core embedding methods ─────────────────────────────

    @abstractmethod
    async def embed_documents(
        self,
        texts: list[str],
        metadata: list[dict[str, Any]] | None = None,
    ) -> BatchEmbeddingResult:
        """Embed a list of document texts.

        Args:
            texts: List of document text strings to embed.
            metadata: Optional metadata for each text (same length as texts).

        Returns:
            BatchEmbeddingResult with vectors, token counts, and any failures.

        Raises:
            EmbeddingServiceUnavailable: Provider is unreachable.
            EmbeddingTimeout: Request exceeded timeout.
            EmbeddingError: Other embedding failures.
        """
        ...

    @abstractmethod
    async def embed_query(self, text: str) -> EmbeddingResult:
        """Embed a single query string.

        Args:
            text: Query text to embed.

        Returns:
            EmbeddingResult with the query vector.

        Raises:
            EmbeddingServiceUnavailable: Provider is unreachable.
            EmbeddingTimeout: Request exceeded timeout.
        """
        ...

    @abstractmethod
    async def batch_embed(
        self,
        texts: list[str],
        batch_size: int = 32,
        metadata: list[dict[str, Any]] | None = None,
    ) -> BatchEmbeddingResult:
        """Embed texts with automatic batching and progress tracking.

        Splits large lists into batches, embeds each batch, collects results,
        and retries individual batches on failure.

        Args:
            texts: Full list of texts to embed.
            batch_size: Number of texts per API call.
            metadata: Optional metadata list.

        Returns:
            BatchEmbeddingResult with all vectors and failure tracking.
        """
        ...

    # ── Health and metadata ───────────────────────────────

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the provider is reachable and responding.

        Returns:
            True if healthy, False otherwise.
        """
        ...

    @abstractmethod
    async def model_info(self) -> EmbeddingProviderInfo:
        """Get metadata about the current model and provider.

        Returns:
            EmbeddingProviderInfo with model details.
        """
        ...

    @abstractmethod
    async def dimension(self) -> int:
        """Get the embedding vector dimension.

        Returns:
            Vector dimension (e.g., 2048 for nv-embed-qa-4).
        """
        ...

    @abstractmethod
    async def max_input_tokens(self) -> int:
        """Get the maximum number of input tokens supported.

        Returns:
            Maximum input token count.
        """
        ...

    @abstractmethod
    async def supported_languages(self) -> list[str]:
        """Get the list of supported language codes.

        Returns:
            List of ISO language codes.
        """
        ...

    @abstractmethod
    def provider_name(self) -> str:
        """Get the provider name identifier.

        Returns:
            Provider name string (e.g. "nvidia_nim").
        """
        ...

    # ── Lifecycle ──────────────────────────────────────────

    @abstractmethod
    async def close(self) -> None:
        """Clean up provider resources (HTTP connections, etc.)."""
        ...
