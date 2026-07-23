"""Embedding & Indexing Layer for the Enterprise RAG Platform.

Transforms processed document chunks into a highly scalable vector index
suitable for enterprise semantic search. Supports NVIDIA NIM embeddings,
Milvus vector database, batch/incremental indexing, embedding cache,
and collection lifecycle management.
"""

from app.embeddings.exceptions import (
    EmbeddingError,
    EmbeddingServiceUnavailable,
    EmbeddingTimeout,
    IndexingError,
    IndexingJobNotFound,
    CollectionNotFound,
    CollectionError,
    CacheError,
)

__all__ = [
    "EmbeddingError",
    "EmbeddingServiceUnavailable",
    "EmbeddingTimeout",
    "IndexingError",
    "IndexingJobNotFound",
    "CollectionNotFound",
    "CollectionError",
    "CacheError",
]
