"""Abstract vector store interface.

All vector database operations go through this interface. Business logic
depends only on VectorStore — never on a concrete implementation like Milvus.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class VectorRecord:
    """A single vector record to be stored."""

    id: str = ""
    vector: list[float] | None = None
    text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    chunk_id: str = ""
    document_id: str = ""
    chunk_index: int = 0
    page_number: int | None = None
    section_title: str | None = None
    language: str | None = None
    checksum: str = ""
    version: int = 1
    source: str = ""
    embedding_model: str = ""
    created_at: str = ""


@dataclass
class VectorSearchResult:
    """Result of a vector similarity search."""

    id: str = ""
    score: float = 0.0
    text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    chunk_id: str = ""
    document_id: str = ""
    chunk_index: int = 0


class VectorStore(ABC):
    """Abstract vector database provider.

    All methods are async. Implementations handle connection management,
    batching, retry, and error conversion internally.
    """

    @abstractmethod
    async def create_collection(
        self,
        name: str,
        dimension: int = 2048,
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new collection if it doesn't exist.

        Args:
            name: Collection name.
            dimension: Vector embedding dimension.
            schema: Optional custom schema definition.

        Returns:
            Collection info dict.
        """
        ...

    @abstractmethod
    async def delete_collection(self, name: str) -> None:
        """Delete a collection and all its vectors."""
        ...

    @abstractmethod
    async def collection_exists(self, name: str) -> bool:
        """Check if a collection exists."""
        ...

    @abstractmethod
    async def list_collections(self) -> list[str]:
        """List all collection names."""
        ...

    @abstractmethod
    async def upsert_vectors(
        self,
        collection_name: str,
        vectors: list[VectorRecord],
        batch_size: int = 100,
    ) -> int:
        """Insert or update vectors in a collection.

        Args:
            collection_name: Target collection.
            vectors: Vector records to upsert.
            batch_size: Number of vectors per batch insert.

        Returns:
            Number of vectors successfully upserted.
        """
        ...

    @abstractmethod
    async def delete_vectors(
        self,
        collection_name: str,
        ids: list[str] | None = None,
        filter_expr: str | None = None,
    ) -> int:
        """Delete vectors by IDs or filter expression.

        Args:
            collection_name: Target collection.
            ids: Optional list of vector IDs to delete.
            filter_expr: Optional filter expression (e.g., "document_id == 'xxx'").

        Returns:
            Number of vectors deleted.
        """
        ...

    @abstractmethod
    async def get_vector(
        self,
        collection_name: str,
        id: str,
    ) -> VectorRecord | None:
        """Get a single vector record by ID."""
        ...

    @abstractmethod
    async def get_vector_count(self, collection_name: str) -> int:
        """Get the total number of vectors in a collection."""
        ...

    @abstractmethod
    async def collection_stats(self, collection_name: str) -> dict[str, Any]:
        """Get detailed statistics for a collection."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the vector store is reachable and responding."""
        ...

    @abstractmethod
    async def search(
        self,
        collection_name: str,
        query_vector: list[float],
        top_k: int = 10,
        filter_expr: str | None = None,
        output_fields: list[str] | None = None,
    ) -> list[VectorSearchResult]:
        """Search for nearest neighbors in a collection.

        Args:
            collection_name: Collection name (without prefix).
            query_vector: Query embedding vector.
            top_k: Number of results to return.
            filter_expr: Optional Milvus filter expression.
            output_fields: Fields to include in results.

        Returns:
            List of VectorSearchResult sorted by similarity (descending).

        Raises:
            CollectionNotFound: If the collection does not exist.
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close connections and release resources."""
        ...
