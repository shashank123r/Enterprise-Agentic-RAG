"""Milvus VectorStore implementation.

All synchronous pymilvus calls are offloaded to a thread executor
so the event loop is never blocked. Follows Clean Architecture —
business logic depends only on the abstract VectorStore interface.
"""

import asyncio
import uuid
from collections.abc import Callable
from functools import partial
from typing import Any, TypeVar

from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    MilvusException,
    connections,
    utility,
)

from app.core.logging import get_logger
from app.vector_stores.base import VectorRecord, VectorSearchResult, VectorStore
from app.vector_stores.exceptions import (
    BatchInsertError,
    CollectionNotFound,
    VectorDimensionMismatch,
    VectorStoreAuthError,
    VectorStoreError,
    VectorStoreUnavailable,
)

logger = get_logger(__name__)

T = TypeVar("T")


class MilvusVectorStore(VectorStore):
    """Milvus-backed VectorStore implementation.

    All synchronous pymilvus calls run through ``_run_sync`` to avoid
    blocking the async event loop. Connection pooling, retry, and
    error conversion are handled internally.

    The class is fully async-safe: no mutable shared state is accessed
    without proper synchronization.
    """

    def __init__(
        self,
        alias: str = "default",
        host: str = "localhost",
        port: int = 19530,
        user: str = "",
        password: str = "",
        collection_prefix: str = "rag_",
        default_dimension: int = 2048,
        connect_timeout: int = 10,
    ) -> None:
        self._alias = alias
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._collection_prefix = collection_prefix
        self._default_dimension = default_dimension
        self._connect_timeout = connect_timeout
        self._connected = False
        self._collection_cache: dict[str, Collection] = {}
        self._lock = asyncio.Lock()

    # ── Sync offloading ────────────────────────

    @staticmethod
    async def _run_sync(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Run a synchronous function in a thread executor.

        This is the single point of offloading for all pymilvus calls.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))

    # ── Connection lifecycle ───────────────────

    async def connect(self) -> None:
        """Establish connection to Milvus with retry.

        Raises:
            VectorStoreUnavailable: If connection fails after retries.
            VectorStoreAuthError: If authentication fails.
        """
        async with self._lock:
            if self._connected:
                return

            try:
                connect_kwargs: dict[str, Any] = {
                    "alias": self._alias,
                    "host": self._host,
                    "port": self._port,
                    "timeout": self._connect_timeout,
                }
                if self._user:
                    connect_kwargs["user"] = self._user
                if self._password:
                    connect_kwargs["password"] = self._password

                await self._run_sync(connections.connect, **connect_kwargs)
                self._connected = True
                logger.info(
                    "Connected to Milvus",
                    host=self._host,
                    port=self._port,
                    alias=self._alias,
                )
            except MilvusException as e:
                if "authentication" in str(e).lower() or "unauthorized" in str(e).lower():
                    raise VectorStoreAuthError(f"Milvus authentication failed: {e}")
                raise VectorStoreUnavailable(f"Failed to connect to Milvus: {e}")
            except ConnectionError as e:
                raise VectorStoreUnavailable(f"Milvus connection refused: {e}")
            except Exception as e:
                raise VectorStoreUnavailable(f"Unexpected connection error: {e}")

    async def close(self) -> None:
        """Disconnect from Milvus and release resources."""
        async with self._lock:
            if not self._connected:
                return
            try:
                await self._run_sync(connections.disconnect, self._alias)
            except Exception as e:
                logger.warning("Error disconnecting from Milvus", exc_info=e)
            finally:
                self._connected = False
                self._collection_cache.clear()
                logger.info("Disconnected from Milvus")

    async def health_check(self) -> bool:
        """Check if Milvus is reachable and responding.

        Returns:
            True if healthy, False otherwise.
        """
        try:
            if not self._connected:
                await self.connect()
            # A lightweight check — list collections is fast
            await self._run_sync(utility.list_collections, using=self._alias)
            return True
        except Exception as e:
            logger.warning("Milvus health check failed", exc_info=e)
            return False

    # ── Collection helpers ─────────────────────

    def _prefixed_name(self, name: str) -> str:
        """Apply the collection prefix."""
        return f"{self._collection_prefix}{name}"

    def _strip_prefix(self, prefixed: str) -> str:
        """Remove the collection prefix."""
        if prefixed.startswith(self._collection_prefix):
            return prefixed[len(self._collection_prefix) :]
        return prefixed

    def _build_schema(
        self,
        dimension: int,
        schema_override: dict[str, Any] | None = None,
    ) -> CollectionSchema:
        """Build a default document-chunk schema.

        Args:
            dimension: Embedding vector dimension.
            schema_override: Optional dict to override default field types/sizes.

        Returns:
            A CollectionSchema suitable for document chunks.
        """
        chunk_id_max_len = schema_override.get("chunk_id_max_len", 64) if schema_override else 64
        doc_id_max_len = schema_override.get("document_id_max_len", 64) if schema_override else 64
        text_max_len = schema_override.get("text_max_len", 65535) if schema_override else 65535
        model_max_len = schema_override.get("model_max_len", 128) if schema_override else 128
        source_max_len = schema_override.get("source_max_len", 256) if schema_override else 256

        fields = [
            FieldSchema(
                name="id",
                dtype=DataType.INT64,
                is_primary=True,
                auto_id=True,
                description="Auto-generated primary key",
            ),
            FieldSchema(
                name="chunk_id",
                dtype=DataType.VARCHAR,
                max_length=chunk_id_max_len,
                description="Unique chunk identifier (UUID)",
            ),
            FieldSchema(
                name="document_id",
                dtype=DataType.VARCHAR,
                max_length=doc_id_max_len,
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
                max_length=text_max_len,
                description="Chunk text content",
            ),
            FieldSchema(
                name="metadata",
                dtype=DataType.JSON,
                description="Rich chunk metadata",
            ),
            FieldSchema(
                name="page_number",
                dtype=DataType.INT64,
                description="Source page number",
            ),
            FieldSchema(
                name="chunk_index",
                dtype=DataType.INT64,
                description="Chunk position within document",
            ),
            FieldSchema(
                name="section_title",
                dtype=DataType.VARCHAR,
                max_length=256,
                description="Section heading",
            ),
            FieldSchema(
                name="language",
                dtype=DataType.VARCHAR,
                max_length=16,
                description="Detected language code",
            ),
            FieldSchema(
                name="checksum",
                dtype=DataType.VARCHAR,
                max_length=64,
                description="Content checksum (SHA-256)",
            ),
            FieldSchema(
                name="version",
                dtype=DataType.INT64,
                description="Document version number",
            ),
            FieldSchema(
                name="source",
                dtype=DataType.VARCHAR,
                max_length=source_max_len,
                description="Source filename or URL",
            ),
            FieldSchema(
                name="embedding_model",
                dtype=DataType.VARCHAR,
                max_length=model_max_len,
                description="Model used for embedding",
            ),
        ]
        return CollectionSchema(
            fields=fields,
            description="Document chunks with embeddings and rich metadata",
            enable_dynamic_field=False,
        )

    # ── Collection management ──────────────────

    async def create_collection(
        self,
        name: str,
        dimension: int | None = None,
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a collection if it doesn't exist.

        Args:
            name: Collection name (without prefix).
            dimension: Embedding dimension. Uses default if not provided.
            schema: Optional schema overrides (field max lengths, etc.).

        Returns:
            Collection info dict.

        Raises:
            VectorStoreUnavailable: If connection fails.
        """
        await self._ensure_connected()
        collection_name = self._prefixed_name(name)
        actual_dim = dimension or self._default_dimension

        exists = await self._run_sync(utility.has_collection, collection_name, using=self._alias)
        if exists:
            logger.info("Collection already exists", name=collection_name)
            collection = Collection(collection_name, using=self._alias)
            self._collection_cache[name] = collection
            return await self.collection_stats(name)

        milvus_schema = self._build_schema(actual_dim, schema_override=schema)

        try:
            collection = await self._run_sync(
                Collection,
                name=collection_name,
                schema=milvus_schema,
                using=self._alias,
            )

            # Create IVF_FLAT index for efficient ANN search
            index_params = {
                "metric_type": "COSINE",
                "index_type": "IVF_FLAT",
                "params": {"nlist": 1024},
            }
            await self._run_sync(
                collection.create_index,
                field_name="vector",
                index_params=index_params,
            )

            await self._run_sync(collection.load)
            self._collection_cache[name] = collection

            logger.info(
                "Created collection",
                name=collection_name,
                dimension=actual_dim,
            )
            return await self.collection_stats(name)

        except MilvusException as e:
            raise VectorStoreError(f"Failed to create collection '{collection_name}': {e}")
        except Exception as e:
            raise VectorStoreError(f"Unexpected error creating collection: {e}")

    async def delete_collection(self, name: str) -> None:
        """Delete a collection and all its vectors.

        Args:
            name: Collection name (without prefix).

        Raises:
            CollectionNotFound: If the collection does not exist.
        """
        collection_name = self._prefixed_name(name)
        exists = await self._run_sync(utility.has_collection, collection_name, using=self._alias)
        if not exists:
            raise CollectionNotFound(name)

        try:
            await self._run_sync(utility.drop_collection, collection_name, using=self._alias)
            self._collection_cache.pop(name, None)
            logger.info("Dropped collection", name=collection_name)
        except MilvusException as e:
            raise VectorStoreError(f"Failed to delete collection '{collection_name}': {e}")

    async def collection_exists(self, name: str) -> bool:
        """Check if a collection exists."""
        collection_name = self._prefixed_name(name)
        try:
            return await self._run_sync(utility.has_collection, collection_name, using=self._alias)
        except MilvusException:
            return False

    async def list_collections(self) -> list[str]:
        """List all collection names (with prefix stripped)."""
        try:
            prefixed = await self._run_sync(utility.list_collections, using=self._alias)
            return [
                self._strip_prefix(c) for c in prefixed if c.startswith(self._collection_prefix)
            ]
        except MilvusException as e:
            raise VectorStoreError(f"Failed to list collections: {e}")

    async def collection_stats(self, collection_name: str) -> dict[str, Any]:
        """Get detailed statistics for a collection.

        Args:
            collection_name: Collection name (without prefix).

        Returns:
            Dict with count, schema fields, index info, and existence flag.

        Raises:
            CollectionNotFound: If the collection does not exist.
        """
        prefixed = self._prefixed_name(collection_name)
        exists = await self._run_sync(utility.has_collection, prefixed, using=self._alias)
        if not exists:
            return {"exists": False, "name": collection_name}

        try:
            collection = Collection(prefixed, using=self._alias)
            schema_fields = {field.name: str(field.dtype) for field in collection.schema.fields}
            indexes = [
                {"field": idx.field_name, "params": idx.params} for idx in collection.indexes
            ]
            num_entities = await self._run_sync(lambda: collection.num_entities)

            return {
                "exists": True,
                "name": collection_name,
                "prefixed_name": prefixed,
                "num_entities": num_entities,
                "schema": schema_fields,
                "indexes": indexes,
            }
        except MilvusException as e:
            raise VectorStoreError(f"Failed to get stats for '{prefixed}': {e}")

    # ── Vector CRUD ────────────────────────────

    async def upsert_vectors(
        self,
        collection_name: str,
        vectors: list[VectorRecord],
        batch_size: int = 100,
    ) -> int:
        """Insert or update vectors in a collection.

        Args:
            collection_name: Target collection (without prefix).
            vectors: Vector records to upsert.
            batch_size: Number of vectors per batch insert.

        Returns:
            Number of vectors successfully upserted.

        Raises:
            CollectionNotFound: If the collection does not exist.
            VectorDimensionMismatch: If vector dimensions don't match.
            BatchInsertError: If batch insert fails.
        """
        if not vectors:
            return 0

        prefixed = self._prefixed_name(collection_name)
        collection = await self._get_cached_collection(collection_name, prefixed)

        # Validate dimensions — lookup vector field by name, not index
        expected_dim: int | None = None
        for field in collection.schema.fields:
            if field.name == "vector":
                expected_dim = field.params.get("dim")
                break
        for record in vectors:
            if record.vector is not None and expected_dim is not None:
                if len(record.vector) != expected_dim:
                    raise VectorDimensionMismatch(
                        expected=expected_dim,
                        actual=len(record.vector),
                    )

        total_upserted = 0
        errors: list[str] = []

        # Process in batches
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i : i + batch_size]
            try:
                milvus_entities = self._records_to_entities(batch)
                await self._run_sync(collection.insert, milvus_entities)
                total_upserted += len(batch)
            except MilvusException as e:
                errors.append(f"Batch {i // batch_size} failed: {e}")
                logger.error("Batch insert failed", batch_index=i // batch_size, error=str(e))
            except Exception as e:
                errors.append(f"Batch {i // batch_size} unexpected error: {e}")
                logger.error(
                    "Unexpected batch insert error", batch_index=i // batch_size, error=str(e)
                )

        # Flush after all batches
        if total_upserted > 0:
            try:
                await self._run_sync(collection.flush)
            except MilvusException as e:
                logger.warning("Flush failed after batch insert", error=str(e))

        if errors:
            raise BatchInsertError(
                message=f"Batch insert completed with {len(errors)} failed batch(es)",
                attempted=len(vectors),
                succeeded=total_upserted,
                errors=errors,
            )

        logger.info(
            "Upserted vectors",
            collection=collection_name,
            count=total_upserted,
        )
        return total_upserted

    async def delete_vectors(
        self,
        collection_name: str,
        ids: list[str] | None = None,
        filter_expr: str | None = None,
    ) -> int:
        """Delete vectors by chunk IDs or filter expression.

        Args:
            collection_name: Target collection (without prefix).
            ids: Optional list of chunk_id values to delete.
            filter_expr: Optional filter expression (e.g., "document_id == 'xxx'").

        Returns:
            Number of vectors deleted.

        Raises:
            CollectionNotFound: If the collection does not exist.
        """
        prefixed = self._prefixed_name(collection_name)
        collection = await self._get_cached_collection(collection_name, prefixed)

        expr: str | None = None

        if ids:
            # Build OR expression from IDs
            id_exprs = [f'chunk_id == "{cid}"' for cid in ids]
            expr = " || ".join(id_exprs)

        if filter_expr and expr:
            expr = f"({expr}) && ({filter_expr})"
        elif filter_expr:
            expr = filter_expr

        if not expr:
            raise VectorStoreError("Either 'ids' or 'filter_expr' must be provided")

        try:
            result = await self._run_sync(collection.delete, expr)
            count = result if isinstance(result, int) else 0
            logger.info("Deleted vectors", collection=collection_name, count=count, expr=expr)
            return count
        except MilvusException as e:
            raise VectorStoreError(f"Failed to delete vectors: {e}")

    async def get_vector(
        self,
        collection_name: str,
        id: str,
    ) -> VectorRecord | None:
        """Get a single vector record by chunk_id.

        Args:
            collection_name: Target collection (without prefix).
            id: Chunk ID to look up.

        Returns:
            VectorRecord if found, None otherwise.
        """
        prefixed = self._prefixed_name(collection_name)
        collection = await self._get_cached_collection(collection_name, prefixed)

        try:
            expr = f'chunk_id == "{id}"'
            results = await self._run_sync(
                collection.query,
                expr=expr,
                output_fields=["*"],
            )
            if not results:
                return None
            return self._entity_to_record(results[0])
        except MilvusException as e:
            logger.warning("Failed to get vector", chunk_id=id, error=str(e))
            return None

    # ── Vector search ────────────────────────────

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
            output_fields: Optional list of fields to return.

        Returns:
            List of VectorSearchResult sorted by similarity (descending).

        Raises:
            CollectionNotFound: If the collection does not exist.
        """
        prefixed = self._prefixed_name(collection_name)
        collection = await self._get_cached_collection(collection_name, prefixed)

        search_params = {
            "metric_type": "COSINE",
            "params": {"nprobe": 10},
        }

        fields = output_fields or [
            "chunk_id",
            "document_id",
            "text",
            "metadata",
            "page_number",
            "chunk_index",
            "section_title",
            "language",
            "checksum",
            "version",
            "source",
            "embedding_model",
        ]

        try:
            results = await self._run_sync(
                collection.search,
                data=[query_vector],
                anns_field="vector",
                param=search_params,
                limit=top_k,
                expr=filter_expr or None,
                output_fields=fields,
            )

            if not results:
                return []

            hits = results[0]  # First (only) query result
            search_results: list[VectorSearchResult] = []
            for hit in hits:
                entity = hit.entity
                metadata = {}
                if hasattr(entity, "metadata") and entity.metadata is not None:
                    if isinstance(entity.metadata, dict):
                        metadata = entity.metadata
                    else:
                        try:
                            import json

                            metadata = json.loads(entity.metadata)
                        except (json.JSONDecodeError, TypeError):
                            metadata = {"raw": str(entity.metadata)}

                search_results.append(
                    VectorSearchResult(
                        id=str(hit.id),
                        score=hit.score,
                        text=getattr(entity, "text", ""),
                        metadata=metadata,
                        chunk_id=getattr(entity, "chunk_id", ""),
                        document_id=getattr(entity, "document_id", ""),
                        chunk_index=getattr(entity, "chunk_index", 0),
                    )
                )

            logger.debug(
                "Vector search complete",
                collection=collection_name,
                top_k=top_k,
                results=len(search_results),
            )
            return search_results

        except MilvusException as e:
            logger.error("Vector search failed", collection=collection_name, error=str(e))
            raise VectorStoreError(f"Vector search failed: {e}")

    async def get_vector_count(self, collection_name: str) -> int:
        """Get the total number of vectors in a collection.

        Args:
            collection_name: Collection name (without prefix).

        Returns:
            Vector count, or 0 if collection doesn't exist.
        """
        try:
            stats = await self.collection_stats(collection_name)
            return stats.get("num_entities", 0)
        except (CollectionNotFound, VectorStoreError):
            return 0

    # ── Internal helpers ───────────────────────

    async def _ensure_connected(self) -> None:
        """Ensure connection is established before operations."""
        if not self._connected:
            await self.connect()

    async def _get_cached_collection(
        self,
        name: str,
        prefixed: str,
    ) -> Collection:
        """Get or cache a Collection handle.

        Args:
            name: Unprefixed collection name (cache key).
            prefixed: Prefixed collection name (Milvus name).

        Returns:
            Cached or freshly loaded Collection instance.

        Raises:
            CollectionNotFound: If the collection does not exist.
        """
        if name in self._collection_cache:
            return self._collection_cache[name]

        await self._ensure_connected()

        exists = await self._run_sync(utility.has_collection, prefixed, using=self._alias)
        if not exists:
            raise CollectionNotFound(name)

        collection = Collection(prefixed, using=self._alias)
        await self._run_sync(collection.load)
        self._collection_cache[name] = collection
        return collection

    def _records_to_entities(self, records: list[VectorRecord]) -> list[dict[str, Any]]:
        """Convert VectorRecords to Milvus entity dicts.

        Args:
            records: List of VectorRecord instances.

        Returns:
            List of dicts suitable for collection.insert().
        """
        entities: list[dict[str, Any]] = []

        for record in records:
            entity: dict[str, Any] = {
                "chunk_id": record.chunk_id or str(uuid.uuid4()),
                "document_id": record.document_id,
                "vector": record.vector or [],
                "text": record.text,
                "metadata": record.metadata,
                "page_number": record.page_number or 0,
                "chunk_index": record.chunk_index,
                "section_title": record.section_title or "",
                "language": record.language or "unknown",
                "checksum": record.checksum or "",
                "version": record.version,
                "source": record.source or "",
                "embedding_model": record.embedding_model or "",
            }
            entities.append(entity)

        return entities

    def _entity_to_record(self, entity: dict[str, Any]) -> VectorRecord:
        """Convert a Milvus entity dict to a VectorRecord.

        Args:
            entity: Milvus query result as a dict.

        Returns:
            A populated VectorRecord.
        """
        return VectorRecord(
            id=str(entity.get("id", "")),
            vector=entity.get("vector"),
            text=entity.get("text", ""),
            metadata=entity.get("metadata", {}),
            chunk_id=entity.get("chunk_id", ""),
            document_id=entity.get("document_id", ""),
            chunk_index=entity.get("chunk_index", 0),
            page_number=entity.get("page_number"),
            section_title=entity.get("section_title"),
            language=entity.get("language"),
            checksum=entity.get("checksum", ""),
            version=entity.get("version", 1),
            source=entity.get("source", ""),
            embedding_model=entity.get("embedding_model", ""),
            created_at="",
        )
