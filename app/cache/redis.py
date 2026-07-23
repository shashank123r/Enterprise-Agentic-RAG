"""Redis connection manager with connection pooling and retry logic."""

from typing import Any

from redis.asyncio import ConnectionPool, Redis
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class RedisManager:
    """Manages Redis connection pool and provides a client interface."""

    def __init__(self) -> None:
        self._pool: ConnectionPool | None = None
        self._client: Redis | None = None

    async def initialize(self) -> None:
        """Create the connection pool and test connectivity."""
        try:
            self._pool = ConnectionPool.from_url(
                settings.redis_url,
                socket_connect_timeout=settings.REDIS_SOCKET_TIMEOUT,
                socket_keepalive=True,
                max_connections=50,
                decode_responses=True,
            )
            self._client = Redis(connection_pool=self._pool)

            # Verify connectivity
            await self._ping()
            logger.info(
                "Redis connected",
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
            )
        except Exception as e:
            logger.error("Failed to connect to Redis", exc_info=e)
            raise

    async def close(self) -> None:
        """Close the Redis connection pool."""
        if self._client:
            await self._client.aclose()
        if self._pool:
            await self._pool.aclose()
        logger.info("Redis connection closed")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=0.5, max=3),
    )
    async def _ping(self) -> bool:
        """Ping Redis to verify connectivity with retry."""
        if self._client is None:
            return False
        return await self._client.ping()

    @property
    def client(self) -> Redis:
        """Get the Redis client instance.

        Raises:
            RuntimeError: If Redis is not initialized.
        """
        if self._client is None:
            raise RuntimeError(
                "Redis client not initialized. Call `initialize()` first."
            )
        return self._client

    # ── Convenience Methods ───────────────────

    async def set(
        self,
        key: str,
        value: str,
        ttl: int | None = None,
    ) -> bool:
        """Set a key with optional TTL."""
        return await self.client.set(key, value, ex=ttl)

    async def get(self, key: str) -> str | None:
        """Get a key's value."""
        return await self.client.get(key)

    async def delete(self, key: str) -> bool:
        """Delete a key."""
        return await self.client.delete(key) > 0

    async def exists(self, key: str) -> bool:
        """Check if a key exists."""
        return await self.client.exists(key) > 0

    async def expire(self, key: str, ttl: int) -> bool:
        """Set TTL on an existing key."""
        return await self.client.expire(key, ttl)

    async def incr(self, key: str) -> int:
        """Increment a key's value."""
        return await self.client.incr(key)

    async def lpush(self, key: str, *values: str) -> int:
        """Push values to the head of a list."""
        return await self.client.lpush(key, *values)

    async def rpop(self, key: str) -> str | None:
        """Pop a value from the tail of a list."""
        return await self.client.rpop(key)

    async def publish(self, channel: str, message: str) -> int:
        """Publish a message to a channel."""
        return await self.client.publish(channel, message)

    async def hset(
        self,
        name: str,
        key: str,
        value: Any,
    ) -> int:
        """Set a hash field."""
        return await self.client.hset(name, key, value)

    async def hget(self, name: str, key: str) -> Any | None:
        """Get a hash field."""
        return await self.client.hget(name, key)

    async def hgetall(self, name: str) -> dict[str, Any]:
        """Get all fields of a hash."""
        return await self.client.hgetall(name)  # type: ignore[return-value]


# Global Redis manager instance
redis_manager = RedisManager()
