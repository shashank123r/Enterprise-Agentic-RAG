"""Storage abstraction layer — pluggable providers for Local, S3, Azure, GCS, MinIO.

Usage:
    from app.storage import StorageProvider, get_storage_provider

    storage = await get_storage_provider()
    await storage.save("documents/abc-123", content)
"""

from app.storage.base import StorageProvider
from app.storage.exceptions import (
    StorageError,
    StorageFileNotFound,
    StoragePermissionDenied,
    StorageQuotaExceeded,
    StorageUnavailable,
)
from app.storage.factory import create_storage_provider
from app.storage.models import StorageFileInfo

__all__ = [
    "StorageProvider",
    "StorageFileInfo",
    "StorageError",
    "StorageFileNotFound",
    "StoragePermissionDenied",
    "StorageQuotaExceeded",
    "StorageUnavailable",
    "create_storage_provider",
]
