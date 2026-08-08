"""Vector store provider factory.

Creates the configured VectorStore instance based on settings.
New providers can be added without modifying business logic.
"""

from collections.abc import AsyncGenerator

from app.core.config import settings
from app.core.logging import get_logger
from app.vector_stores.base import VectorStore
from app.vector_stores.collection_manager import CollectionManager
from app.vector_stores.exceptions import VectorStoreError

logger = get_logger(__name__)


# Module-level singleton — initialized on first use
_vector_store: VectorStore | None = None
_collection_manager: CollectionManager | None = None


async def create_vector_store() -> VectorStore:
    """Create and return the configured VectorStore instance.

    Returns:
        An initialized VectorStore (MilvusVectorStore).

    Raises:
        VectorStoreError: If the configured provider is unknown.
    """
    provider = settings.VECTOR_STORE_PROVIDER.lower()

    if provider == "milvus":
        from app.vector_stores.milvus import MilvusVectorStore

        store = MilvusVectorStore(
            alias=settings.MILVUS_ALIAS,
            host=settings.MILVUS_HOST,
            port=settings.MILVUS_PORT,
            user=settings.MILVUS_USERNAME,
            password=settings.MILVUS_PASSWORD,
            collection_prefix=settings.MILVUS_COLLECTION_PREFIX,
            default_dimension=settings.VECTOR_STORE_DIMENSION,
            connect_timeout=settings.MILVUS_CONNECT_TIMEOUT,
        )
        await store.connect()
        logger.info(
            "Created MilvusVectorStore",
            host=settings.MILVUS_HOST,
            port=settings.MILVUS_PORT,
            alias=settings.MILVUS_ALIAS,
        )
        return store

    raise VectorStoreError(f"Unknown vector store provider: '{provider}'. " f"Supported: milvus")


async def get_vector_store() -> AsyncGenerator[VectorStore]:
    """FastAPI dependency — provides the singleton VectorStore.

    Usage::
        @router.get("/collections")
        async def list_collections(
            store: VectorStore = Depends(get_vector_store),
        ):
            ...
    """
    global _vector_store
    if _vector_store is None:
        _vector_store = await create_vector_store()
    try:
        yield _vector_store
    finally:
        pass  # Connection lifecycle managed by lifespan


async def get_collection_manager() -> AsyncGenerator[CollectionManager]:
    """FastAPI dependency — provides the CollectionManager wrapper.

    Usage::
        @router.post("/collections")
        async def create_collection(
            manager: CollectionManager = Depends(get_collection_manager),
        ):
            ...
    """
    global _collection_manager
    if _collection_manager is None:
        # Get the singleton vector store via its async generator
        async for store in get_vector_store():
            _collection_manager = CollectionManager(store)
            break
    yield _collection_manager  # type: ignore[misc]


async def close_vector_store() -> None:
    """Close the vector store connection. Called during application shutdown."""
    global _vector_store, _collection_manager
    if _vector_store is not None:
        try:
            await _vector_store.close()
        except Exception as e:
            logger.error("Error closing vector store", exc_info=e)
        finally:
            _vector_store = None
            _collection_manager = None
            logger.info("Vector store connection closed")
