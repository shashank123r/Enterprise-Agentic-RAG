"""Collection lifecycle manager.

Handles collection creation, versioning, migration, rebuild, and deletion.
Supports multiple embedding models — each model+dimension pair can have
its own collection or a versioned collection namespace.
"""

import re
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.vector_stores.base import VectorStore
from app.vector_stores.exceptions import (
    CollectionAlreadyExists,
    CollectionNotFound,
    CollectionNotReady,
    IndexError_,
    VectorStoreError,
)

logger = get_logger(__name__)

# Pattern: collection_name_v{dimension}_v{version}
_COLLECTION_VERSION_PATTERN = re.compile(r"^(.+)_v(\d+)_v(\d+)$")


class CollectionManager:
    """Manages vector collection lifecycles.

    Responsibilities:
        - Create collections with consistent naming conventions.
        - Version collections so schema changes don't break existing data.
        - Migrate data between collection versions.
        - Rebuild collections from source data.
        - Delete collections with safety checks.
        - Validate collection health.

    Usage::
        manager = CollectionManager(vector_store)
        info = await manager.create("documents", dimension=2048)
        versioned = await manager.create_versioned("documents", dimension=2048)
    """

    def __init__(self, vector_store: VectorStore) -> None:
        self._store = vector_store
        self._default_dimension = 2048

    # ── Create ─────────────────────────────────

    async def create(
        self,
        name: str,
        dimension: int | None = None,
        schema: dict[str, Any] | None = None,
        if_not_exists: bool = True,
    ) -> dict[str, Any]:
        """Create a collection.

        Args:
            name: Collection name.
            dimension: Embedding vector dimension.
            schema: Optional schema overrides.
            if_not_exists: If True, return existing collection info instead of error.

        Returns:
            Collection stats dict.

        Raises:
            CollectionAlreadyExists: If if_not_exists is False and collection exists.
        """
        actual_dim = dimension or self._default_dimension

        exists = await self._store.collection_exists(name)
        if exists:
            if if_not_exists:
                return await self._store.collection_stats(name)
            raise CollectionAlreadyExists(name)

        return await self._store.create_collection(name, dimension=actual_dim, schema=schema)

    async def create_versioned(
        self,
        base_name: str,
        dimension: int | None = None,
        version: int | None = None,
    ) -> dict[str, Any]:
        """Create a versioned collection: ``{base_name}_v{dim}_v{version}``.

        Versioning isolates collections by embedding dimension and schema version.
        This allows safe schema migrations without breaking existing indexed data.

        Args:
            base_name: Base collection name.
            dimension: Embedding dimension.
            version: Schema version. Auto-increments if not provided.

        Returns:
            Collection stats dict.
        """
        actual_dim = dimension or self._default_dimension

        if version is None:
            version = await self._next_version(base_name, actual_dim)

        versioned_name = f"{base_name}_v{actual_dim}_v{version}"
        return await self.create(versioned_name, dimension=actual_dim, if_not_exists=True)

    # ── Get / List ─────────────────────────────

    async def get(self, name: str) -> dict[str, Any]:
        """Get collection stats.

        Raises:
            CollectionNotFound: If the collection does not exist.
        """
        exists = await self._store.collection_exists(name)
        if not exists:
            raise CollectionNotFound(name)
        return await self._store.collection_stats(name)

    async def list_all(self) -> list[dict[str, Any]]:
        """List all collections with stats."""
        names = await self._store.list_collections()
        stats = []
        for name in names:
            try:
                s = await self._store.collection_stats(name)
                stats.append(s)
            except Exception as e:
                logger.warning("Failed to get stats for collection", name=name, error=str(e))
        return stats

    # ── Delete ─────────────────────────────────

    async def delete(self, name: str, force: bool = False) -> None:
        """Delete a collection.

        Args:
            name: Collection name.
            force: If False, refuses to delete versioned collections without confirmation.

        Raises:
            CollectionNotFound: If the collection does not exist.
        """
        exists = await self._store.collection_exists(name)
        if not exists:
            raise CollectionNotFound(name)

        # Safety: refuse to delete versioned collections unless forced
        if not force and _COLLECTION_VERSION_PATTERN.match(name):
            logger.warning(
                "Refusing to delete versioned collection without force=True",
                name=name,
            )
            raise VectorStoreError(
                f"Use force=True to delete versioned collection '{name}'"
            )

        await self._store.delete_collection(name)
        logger.info("Deleted collection", name=name)

    async def delete_versioned(
        self,
        base_name: str,
        dimension: int,
        version: int,
    ) -> None:
        """Delete a specific versioned collection."""
        versioned_name = f"{base_name}_v{dimension}_v{version}"
        await self.delete(versioned_name, force=True)

    # ── Rebuild ────────────────────────────────

    async def rebuild(
        self,
        name: str,
        dimension: int | None = None,
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Drop and recreate a collection.

        Warning: This destroys all vectors in the collection.

        Args:
            name: Collection name.
            dimension: New embedding dimension.
            schema: Optional schema overrides.

        Returns:
            New collection stats.
        """
        exists = await self._store.collection_exists(name)
        if exists:
            await self._store.delete_collection(name)
            logger.info("Dropped existing collection for rebuild", name=name)

        actual_dim = dimension or self._default_dimension
        return await self._store.create_collection(name, dimension=actual_dim, schema=schema)

    # ── Health ─────────────────────────────────

    async def health(self, name: str) -> dict[str, Any]:
        """Validate a collection's health.

        Returns:
            Dict with health status, vector count, and any warnings.
        """
        try:
            exists = await self._store.collection_exists(name)
            if not exists:
                return {"healthy": False, "error": "not_found"}

            stats = await self._store.collection_stats(name)
            count = stats.get("num_entities", 0)

            warnings: list[str] = []
            if count == 0 and not stats.get("indexes"):
                warnings.append("No vectors and no indexes configured")

            return {
                "healthy": True,
                "name": name,
                "vector_count": count,
                "warnings": warnings,
            }

        except Exception as e:
            return {"healthy": False, "error": str(e)}

    async def health_all(self) -> list[dict[str, Any]]:
        """Validate health of all collections."""
        names = await self._store.list_collections()
        results = []
        for name in names:
            results.append(await self.health(name))
        return results

    # ── Migration ──────────────────────────────

    async def migrate(
        self,
        source_name: str,
        target_name: str,
        batch_size: int = 100,
    ) -> dict[str, Any]:
        """Migrate vectors from one collection to another.

        This is a basic migration that reads from source and writes to
        target. For large collections, consider using Milvus built-in
        tools or bulk export/import.

        Args:
            source_name: Source collection name.
            target_name: Target collection name (must exist).
            batch_size: Vectors per batch.

        Returns:
            Migration stats dict.

        Raises:
            CollectionNotFound: If source or target does not exist.
        """
        if not await self._store.collection_exists(source_name):
            raise CollectionNotFound(source_name)
        if not await self._store.collection_exists(target_name):
            raise CollectionNotFound(target_name)

        # This implementation is a simplified version. Production
        # systems should use Milvus BulkWriter or export/import tools.
        logger.info(
            "Migration stub — use Milvus native tools for production-scale migration",
            source=source_name,
            target=target_name,
        )
        return {
            "source": source_name,
            "target": target_name,
            "status": "not_implemented",
            "note": "Use Milvus bulk export/import for production-scale migration",
        }

    # ── Internal helpers ───────────────────────

    async def _next_version(self, base_name: str, dimension: int) -> int:
        """Determine the next version number for a versioned collection.

        Scans existing collections matching ``{base_name}_v{dim}_v*``
        and returns max(version) + 1, or 1 if none exist.
        """
        all_collections = await self._store.list_collections()
        prefix = f"{base_name}_v{dimension}_v"
        versions = []

        for coll_name in all_collections:
            if coll_name.startswith(prefix):
                suffix = coll_name[len(prefix) :]
                try:
                    versions.append(int(suffix))
                except ValueError:
                    continue

        return max(versions) + 1 if versions else 1
