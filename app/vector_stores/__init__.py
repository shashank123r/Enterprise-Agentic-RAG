"""Vector store abstraction layer — pluggable backends for Milvus, Pinecone, Weaviate, Qdrant.

Business logic depends only on the abstract VectorStore interface.
"""

from app.vector_stores.base import VectorRecord, VectorSearchResult, VectorStore
from app.vector_stores.collection_manager import CollectionManager
from app.vector_stores.exceptions import (
    BatchInsertError,
    CollectionAlreadyExists,
    CollectionNotFound,
    CollectionNotReady,
    VectorDimensionMismatch,
    VectorStoreAuthError,
    VectorStoreError,
    VectorStoreTimeout,
    VectorStoreUnavailable,
)
from app.vector_stores.exceptions import (
    IndexError_ as IndexError,
)
from app.vector_stores.factory import get_collection_manager, get_vector_store

__all__ = [
    # Abstract interface
    "VectorStore",
    "VectorRecord",
    "VectorSearchResult",
    # Collection management
    "CollectionManager",
    # Factories / DI
    "get_vector_store",
    "get_collection_manager",
    # Exceptions
    "VectorStoreError",
    "VectorStoreUnavailable",
    "VectorStoreAuthError",
    "VectorStoreTimeout",
    "CollectionNotFound",
    "CollectionAlreadyExists",
    "CollectionNotReady",
    "VectorDimensionMismatch",
    "BatchInsertError",
    "IndexError",
]
