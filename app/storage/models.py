"""Data models for the storage abstraction layer."""

from datetime import datetime
from typing import Any


class StorageFileInfo:
    """Metadata about a stored file."""

    def __init__(
        self,
        path: str,
        size_bytes: int = 0,
        modified_at: datetime | None = None,
        is_directory: bool = False,
        checksum: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.path = path
        self.size_bytes = size_bytes
        self.modified_at = modified_at
        self.is_directory = is_directory
        self.checksum = checksum
        self.metadata = metadata or {}

    def __repr__(self) -> str:
        return (
            f"StorageFileInfo(path={self.path}, size={self.size_bytes}, "
            f"is_dir={self.is_directory})"
        )
