"""Storage-specific exceptions for the abstraction layer."""


class StorageError(Exception):
    """Base exception for all storage-related errors."""

    def __init__(self, message: str, code: str = "storage_error") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class StorageUnavailable(StorageError):
    """Storage backend is unreachable or not responding."""

    def __init__(self, message: str = "Storage backend unavailable") -> None:
        super().__init__(message, code="storage_unavailable")


class StoragePermissionDenied(StorageError):
    """Insufficient permissions to perform the operation."""

    def __init__(self, path: str, message: str | None = None) -> None:
        msg = message or f"Permission denied for storage path: {path}"
        super().__init__(msg, code="storage_permission_denied")


class StorageQuotaExceeded(StorageError):
    """Storage quota has been exceeded."""

    def __init__(self, message: str = "Storage quota exceeded") -> None:
        super().__init__(message, code="storage_quota_exceeded")


class StorageFileNotFound(StorageError):
    """The requested file does not exist in storage."""

    def __init__(self, path: str) -> None:
        super().__init__(
            f"File not found in storage: {path}",
            code="storage_file_not_found",
        )
