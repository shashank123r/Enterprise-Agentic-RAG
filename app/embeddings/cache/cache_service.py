"""Redis-backed embedding cache.

Cache key = ``embed:{checksum}:{model}:{dimension}``
Value = serialised vector (JSON list of floats) + metadata

Cache is automatically invalidated when:
- Document is re-indexed with a new checksum.
- Embedding model changes.
- Embedding dimension changes.

TTL is configurable via ``EMBEDDING_CACHE_TTL_SECONDS``.
"""

import json
from typing import Any

from app.cache.redis import redis_manager
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class EmbeddingCacheService:
    """Redis-backed cache for embedding vectors.

    Designed to reduce redundant API calls to the embedding provider
    when the same chunk content has already been embedded.
    """

    def __init__(
        self,
        enabled: bool = True,
        ttl_seconds: int = 86400,
        prefix: str = "embed",
    ) -> None:
        self._enabled = enabled and settings.EMBEDDING_CACHE_ENABLED
        self._ttl = ttl_seconds or settings.EMBEDDING_CACHE_TTL_SECONDS
        self._prefix = prefix

    # ── Public API ─────────────────────────────

    async def get(
        self,
        checksum: str,
        model: str,
        dimension: int,
    ) -> list[float] | None:
        """Get a cached embedding vector.

        Args:
            checksum: Content checksum (SHA-256).
            model: Embedding model name.
            dimension: Expected vector dimension.

        Returns:
            Cached vector as list of floats, or None if miss.
        """
        if not self._enabled or not checksum:
            return None

        key = self._make_key(checksum, model, dimension)
        try:
            raw = await redis_manager.get(key)
            if raw is None:
                return None

            vector = json.loads(raw)
            if not isinstance(vector, list):
                logger.warning("Cached embedding is not a list", key=key)
                await redis_manager.delete(key)
                return None

            # Extend TTL on access (sliding expiration)
            await redis_manager.expire(key, self._ttl)
            return [float(v) for v in vector]

        except (json.JSONDecodeError, TypeError, ValueError) as e:
            logger.warning("Failed to decode cached embedding", key=key, error=str(e))
            await redis_manager.delete(key)
            return None
        except Exception as e:
            logger.warning("Cache read error (non-fatal)", error=str(e))
            return None

    async def set(
        self,
        checksum: str,
        model: str,
        dimension: int,
        vector: list[float],
    ) -> bool:
        """Cache an embedding vector.

        Args:
            checksum: Content checksum (SHA-256).
            model: Embedding model name.
            dimension: Vector dimension.
            vector: Embedding vector to cache.

        Returns:
            True if cached successfully, False otherwise.
        """
        if not self._enabled or not checksum:
            return False

        key = self._make_key(checksum, model, dimension)
        try:
            raw = json.dumps(vector, ensure_ascii=False)
            return await redis_manager.set(key, raw, ttl=self._ttl)
        except Exception as e:
            logger.warning("Cache write error (non-fatal)", error=str(e))
            return False

    async def invalidate(self, checksum: str) -> bool:
        """Invalidate all cached embeddings for a given checksum.

        Since the key includes model and dimension, we use a scan
        approach to find and delete all matching keys.

        Args:
            checksum: Content checksum to invalidate.

        Returns:
            True if any keys were deleted.
        """
        if not self._enabled or not checksum:
            return False

        pattern = f"{self._prefix}:{checksum}:*"
        try:
            deleted = 0
            cursor = 0
            while True:
                cursor, keys = await redis_manager.client.scan(
                    cursor=cursor, match=pattern, count=100
                )
                if keys:
                    await redis_manager.client.delete(*keys)  # type: ignore[arg-type]
                    deleted += len(keys)
                if cursor == 0:
                    break
            if deleted > 0:
                logger.debug("Invalidated cache entries", checksum=checksum, count=deleted)
            return deleted > 0
        except Exception as e:
            logger.warning("Cache invalidation error (non-fatal)", error=str(e))
            return False

    async def invalidate_document(self, checksums: list[str]) -> int:
        """Invalidate all cached embeddings for a list of checksums.

        Args:
            checksums: List of content checksums to invalidate.

        Returns:
            Total number of cache entries deleted.
        """
        total = 0
        for cksum in checksums:
            if await self.invalidate(cksum):
                total += 1
        return total

    async def get_batch(
        self,
        checksums: list[str],
        model: str,
        dimension: int,
    ) -> dict[int, list[float]]:
        """Get cached embeddings for a batch of checksums.

        Args:
            checksums: List of content checksums.
            model: Embedding model name.
            dimension: Vector dimension.

        Returns:
            Dict mapping index to cached vector (only hits included).
        """
        if not self._enabled:
            return {}

        results: dict[int, list[float]] = {}
        for idx, cksum in enumerate(checksums):
            vector = await self.get(cksum, model, dimension)
            if vector is not None:
                results[idx] = vector
        return results

    async def health_check(self) -> bool:
        """Check if Redis is reachable for caching.

        Returns:
            True if caching is enabled and Redis responds.
        """
        if not self._enabled:
            return True  # Not using cache — no issue
        try:
            return await redis_manager._ping()
        except Exception:
            return False

    # ── Internal ───────────────────────────────

    def _make_key(self, checksum: str, model: str, dimension: int) -> str:
        """Build a deterministic cache key."""
        return f"{self._prefix}:{checksum}:{model}:{dimension}"

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def stats(self) -> dict[str, Any]:
        """Get cache configuration statistics."""
        return {
            "enabled": self._enabled,
            "ttl_seconds": self._ttl,
            "prefix": self._prefix,
        }
