"""Embedding provider factory — creates the correct provider based on configuration.

New providers are added here without modifying any calling code.
"""

from app.core.config import settings
from app.core.logging import get_logger
from app.embeddings.providers.base import EmbeddingProvider

logger = get_logger(__name__)

_provider: EmbeddingProvider | None = None


async def create_embedding_provider() -> EmbeddingProvider:
    """Create and cache the configured embedding provider singleton."""
    global _provider

    if _provider is not None:
        return _provider

    provider_type = settings.EMBEDDING_PROVIDER
    logger.info("Creating embedding provider", provider=provider_type)

    if provider_type == "nvidia_nim":
        from app.embeddings.providers.nvidia_nim import NvidiaNIMEmbeddingProvider

        _provider = NvidiaNIMEmbeddingProvider(
            api_url=str(settings.NVIDIA_NIM_URL) if settings.NVIDIA_NIM_URL else None,
            api_key=settings.NVIDIA_NIM_API_KEY or None,
            model=settings.EMBEDDING_MODEL,
            batch_size=settings.EMBEDDING_BATCH_SIZE,
            max_concurrent=settings.MAX_CONCURRENT_REQUESTS,
            timeout=settings.REQUEST_TIMEOUT,
            max_retries=settings.EMBEDDING_MAX_RETRIES,
            backoff_multiplier=settings.EMBEDDING_BACKOFF_MULTIPLIER,
        )
    elif provider_type == "openai":
        raise NotImplementedError(
            "OpenAI embedding provider is not yet implemented. "
            "Set EMBEDDING_PROVIDER=nvidia_nim to use NVIDIA NIM."
        )
    else:
        raise ValueError(
            f"Unknown embedding provider: {provider_type!r}. "
            f"Supported: nvidia_nim"
        )

    logger.info(
        "Embedding provider initialized",
        provider=provider_type,
        model=settings.EMBEDDING_MODEL,
    )
    return _provider


async def get_embedding_provider() -> EmbeddingProvider:
    """Get the singleton embedding provider (for FastAPI DI or direct use)."""
    global _provider
    if _provider is None:
        _provider = await create_embedding_provider()
    return _provider


async def shutdown_embedding_provider() -> None:
    """Clean up provider resources on application shutdown."""
    global _provider
    if _provider is not None:
        await _provider.close()
        _provider = None
        logger.info("Embedding provider shut down")
