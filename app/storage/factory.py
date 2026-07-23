"""Storage provider factory — creates the correct provider based on configuration.

Future providers (S3, Azure, GCS, MinIO) can be added here without modifying
any calling code.
"""

from app.core.config import settings
from app.core.logging import get_logger
from app.storage.base import StorageProvider

logger = get_logger(__name__)

# Singleton storage provider instance
_storage_provider: StorageProvider | None = None


async def create_storage_provider() -> StorageProvider:
    """Create and return the configured storage provider.

    The provider is created once and cached as a singleton for the
    application lifetime. Call this during application startup.

    Returns:
        Configured StorageProvider instance.
    """
    global _storage_provider

    if _storage_provider is not None:
        return _storage_provider

    provider_type = settings.STORAGE_PROVIDER

    if provider_type == "local":
        from app.storage.local import LocalStorageProvider

        _storage_provider = LocalStorageProvider(
            root_path=settings.STORAGE_ROOT,
            temp_path=settings.STORAGE_TEMP_DIR,
        )
        logger.info(
            "Storage provider initialized",
            provider="local",
            root=settings.STORAGE_ROOT,
        )
    elif provider_type == "s3":
        raise NotImplementedError(
            "S3StorageProvider is not yet implemented. "
            "Set STORAGE_PROVIDER=local to use local storage."
        )
    elif provider_type == "azure":
        raise NotImplementedError(
            "AzureBlobStorageProvider is not yet implemented. "
            "Set STORAGE_PROVIDER=local to use local storage."
        )
    elif provider_type == "gcs":
        raise NotImplementedError(
            "GCSStorageProvider is not yet implemented. "
            "Set STORAGE_PROVIDER=local to use local storage."
        )
    elif provider_type == "minio":
        raise NotImplementedError(
            "MinIOStorageProvider is not yet implemented. "
            "Set STORAGE_PROVIDER=local to use local storage."
        )
    else:
        raise ValueError(
            f"Unknown storage provider: {provider_type!r}. "
            f"Supported: local, s3, azure, gcs, minio"
        )

    return _storage_provider


async def get_storage_provider() -> StorageProvider:
    """Get the singleton storage provider instance (initialized at startup).

    This is used as a FastAPI dependency.

    Returns:
        The application's StorageProvider.
    """
    global _storage_provider
    if _storage_provider is None:
        _storage_provider = await create_storage_provider()
    return _storage_provider


async def shutdown_storage_provider() -> None:
    """Clean up storage provider resources on application shutdown."""
    global _storage_provider
    if _storage_provider is not None:
        await _storage_provider.close()
        _storage_provider = None
        logger.info("Storage provider shut down")
