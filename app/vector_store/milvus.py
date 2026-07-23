"""Milvus vector database integration.

Manages connection lifecycle, collection schemas, and
vector CRUD operations for the RAG pipeline.

⚠️ pymilvus is synchronous. All I/O-bound operations are offloaded
   to a thread executor so the event loop is never blocked.
"""

import asyncio
from collections.abc import Callable
from enum import StrEnum
from functools import partial
from typing import Any, TypeVar

from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class MetricType(StrEnum):
    """Supported vector similarity metrics."""

    COSINE = "COSINE"
    IP = "IP"
    L2 = "L2"


class MilvusManager:
    """Manages Milvus connection lifecycle and collection operations.

    All synchronous pymilvus calls are wrapped with ``_run_sync``
    to keep the async interface non-blocking.
    """

    def __init__(self) -> None:
        self._connected = False
        self._collections: dict[str, Collection] = {}

    @staticmethod
    async def _run_sync(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Run a synchronous function in a thread executor."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
    )
    async def connect(self) -> None:
        """Establish connection to Milvus."""
        if self._connected:
            return

        try:
            await self._run_sync(
                connections.connect,
                alias=settings.MILVUS_ALIAS,
                host=settings.MILVUS_HOST,
                port=settings.MILVUS_PORT,
            )
            self._connected = True
            logger.info(
                "Connected to Milvus",
                host=settings.MILVUS_HOST,
                port=settings.MILVUS_PORT,
            )
        except Exception as e:
            logger.error("Failed to connect to Milvus", exc_info=e)
            raise

    async def disconnect(self) -> None:
        """Disconnect from Milvus."""
        if self._connected:
            await self._run_sync(connections.disconnect, settings.MILVUS_ALIAS)
            self._connected = False
            self._collections.clear()
            logger.info("Disconnected from Milvus")

    @property
    def is_connected(self) -> bool:
        """Check if connected to Milvus."""
        return self._connected

    # ── Collection Management ─────────────────

    def _get_collection_name(self, suffix: str) -> str:
        """Get a prefixed collection name."""
        return f"{settings.MILVUS_COLLECTION_PREFIX}{suffix}"

    def get_document_chunks_schema(self, dimension: int = 2048) -> CollectionSchema:
        """Get the schema for document chunk collections.

        Args:
            dimension: Embedding vector dimension (default 2048 for nv-embed-qa-4).

        Returns:
            CollectionSchema with id, chunk_id, vector, text, and metadata fields.
        """
        fields = [
            FieldSchema(
                name="id",
                dtype=DataType.INT64,
                is_primary=True,
                auto_id=True,
            ),
            FieldSchema(
                name="chunk_id",
                dtype=DataType.VARCHAR,
                max_length=64,
                description="Unique chunk identifier (UUID)",
            ),
            FieldSchema(
                name="document_id",
                dtype=DataType.VARCHAR,
                max_length=64,
                description="Parent document UUID",
            ),
            FieldSchema(
                name="vector",
                dtype=DataType.FLOAT_VECTOR,
                dim=dimension,
                description="Embedding vector",
            ),
            FieldSchema(
                name="text",
                dtype=DataType.VARCHAR,
                max_length=65535,
                description="Chunk text content",
            ),
            FieldSchema(
                name="metadata",
                dtype=DataType.JSON,
                description="Chunk metadata (source, page, position, etc.)",
            ),
            FieldSchema(
                name="chunk_index",
                dtype=DataType.INT64,
                description="Chunk position within document",
            ),
            FieldSchema(
                name="embedding_model",
                dtype=DataType.VARCHAR,
                max_length=128,
                description="Model used for embedding",
            ),
        ]
        return CollectionSchema(
            fields=fields,
            description="Document chunks with embeddings",
            enable_dynamic_field=False,
        )

    async def create_collection(
        self,
        name: str,
        schema: CollectionSchema | None = None,
        dimension: int = 2048,
        metric_type: MetricType = MetricType.COSINE,
    ) -> Collection:
        """Create a collection if it doesn't exist.

        Args:
            name: Collection name (without prefix).
            schema: Optional custom schema. Uses default if not provided.
            dimension: Vector dimension (used only with default schema).
            metric_type: Distance metric for vector index.

        Returns:
            The Collection instance.
        """
        collection_name = self._get_collection_name(name)

        exists = await self._run_sync(utility.has_collection, collection_name)
        if exists:
            collection = Collection(collection_name)
            self._collections[name] = collection
            logger.info("Using existing collection", name=collection_name)
            return collection

        if schema is None:
            schema = self.get_document_chunks_schema(dimension)

        collection = await self._run_sync(
            Collection,
            name=collection_name,
            schema=schema,
            using=settings.MILVUS_ALIAS,
        )

        # Create IVF_FLAT index for efficient search
        index_params = {
            "metric_type": metric_type.value,
            "index_type": "IVF_FLAT",
            "params": {"nlist": 1024},
        }

        await self._run_sync(
            collection.create_index,
            field_name="vector",
            index_params=index_params,
        )

        await self._run_sync(collection.load)

        self._collections[name] = collection
        logger.info(
            "Created collection",
            name=collection_name,
            dimension=dimension,
            metric=metric_type.value,
        )
        return collection

    async def get_collection(self, name: str) -> Collection | None:
        """Get a collection by name."""
        collection_name = self._get_collection_name(name)

        if name in self._collections:
            return self._collections[name]

        exists = await self._run_sync(utility.has_collection, collection_name)
        if exists:
            collection = Collection(collection_name)
            await self._run_sync(collection.load)
            self._collections[name] = collection
            return collection

        return None

    async def drop_collection(self, name: str) -> None:
        """Drop a collection."""
        collection_name = self._get_collection_name(name)
        exists = await self._run_sync(utility.has_collection, collection_name)
        if exists:
            await self._run_sync(utility.drop_collection, collection_name)
            self._collections.pop(name, None)
            logger.info("Dropped collection", name=collection_name)

    # ── CRUD Operations ──────────────────────

    async def insert_chunks(
        self,
        collection_name: str,
        chunks: list[dict[str, Any]],
    ) -> list[int]:
        """Insert chunk vectors into a collection.

        Args:
            collection_name: Collection name (without prefix).
            chunks: List of chunk dicts with vector, text, metadata fields.

        Returns:
            List of auto-generated IDs.
        """
        collection = await self.get_collection(collection_name)
        if collection is None:
            raise ValueError(f"Collection '{collection_name}' not found")

        insert_result = await self._run_sync(collection.insert, chunks)
        await self._run_sync(collection.flush)
        logger.info(
            "Inserted chunks",
            collection=collection_name,
            count=len(chunks),
        )
        return insert_result.primary_keys  # type: ignore[return-value]

    async def search(
        self,
        collection_name: str,
        query_vector: list[float],
        top_k: int = 10,
        expr: str | None = None,
        output_fields: list[str] | None = None,
    ) -> list[list[dict[str, Any]]]:
        """Search for similar vectors.

        Args:
            collection_name: Collection name (without prefix).
            query_vector: Query embedding vector.
            top_k: Number of results to return.
            expr: Optional filter expression (e.g., "document_id == 'xxx'").
            output_fields: Fields to return in results.

        Returns:
            Nested list of search results with scores and field values.
        """
        collection = await self.get_collection(collection_name)
        if collection is None:
            raise ValueError(f"Collection '{collection_name}' not found")

        search_params: dict[str, Any] = {
            "metric_type": "COSINE",
            "params": {"nprobe": 10},
        }

        if output_fields is None:
            output_fields = [
                "chunk_id", "document_id", "text", "metadata", "chunk_index",
            ]

        results = await self._run_sync(
            collection.search,
            data=[query_vector],
            anns_field="vector",
            param=search_params,
            limit=top_k,
            expr=expr,
            output_fields=output_fields,
        )

        return [
            [
                {
                    "id": hit.id,
                    "distance": hit.distance,
                    "score": hit.score,
                    **hit.fields,  # type: ignore[arg-type]
                }
                for hit in result
            ]
            for result in results
        ]

    async def delete_by_document(
        self,
        collection_name: str,
        document_id: str,
    ) -> None:
        """Delete all chunks for a given document."""
        collection = await self.get_collection(collection_name)
        if collection is None:
            logger.warning(
                "Collection not found for deletion",
                collection=collection_name,
                document_id=document_id,
            )
            return

        expr = f'document_id == "{document_id}"'
        await self._run_sync(collection.delete, expr)
        logger.info(
            "Deleted document chunks",
            collection=collection_name,
            document_id=document_id,
        )

    async def count_vectors(
        self,
        collection_name: str,
    ) -> int:
        """Count vectors in a collection."""
        collection = await self.get_collection(collection_name)
        if collection is None:
            return 0
        return await self._run_sync(lambda: collection.num_entities)  # type: ignore[return-value]

    async def collection_stats(self, collection_name: str) -> dict[str, Any]:
        """Get statistics for a collection."""
        collection = await self.get_collection(collection_name)
        if collection is None:
            return {"exists": False}

        schema_fields = {
            field.name: str(field.dtype)
            for field in collection.schema.fields
        }

        indexes = [
            {
                "field": idx.field_name,
                "params": idx.params,
            }
            for idx in collection.indexes
        ]

        return {
            "exists": True,
            "name": collection.name,
            "num_entities": await self._run_sync(lambda: collection.num_entities),
            "schema": schema_fields,
            "indexes": indexes,
        }


# Global Milvus manager instance
milvus_manager = MilvusManager()
