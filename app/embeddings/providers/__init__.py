"""Embedding provider implementations.

Currently supports NVIDIA NIM. Add new providers by implementing
EmbeddingProvider and registering in factory.py.
"""

from app.embeddings.providers.base import EmbeddingProvider, EmbeddingResult, EmbeddingProviderInfo

__all__ = [
    "EmbeddingProvider",
    "EmbeddingResult",
    "EmbeddingProviderInfo",
]
