"""Abstract storage provider — all filesystem operations go through this interface.

The pipeline never knows whether files are stored locally, in S3, Azure Blob,
or Google Cloud Storage. It depends only on this abstract interface.
"""

from abc import ABC, abstractmethod
from typing import BinaryIO

from app.storage.models import StorageFileInfo


class StorageProvider(ABC):
    """Pluggable storage backend for document files, images, and temporary data.

    Every method is async and hides implementation details (local path, S3 key,
    Azure blob name, etc.).
    """

    @abstractmethod
    async def save(self, path: str, content: bytes) -> str:
        """Write bytes to the given storage path.

        Args:
            path: Storage path (relative to storage root).
            content: Raw bytes to write.

        Returns:
            The full storage path of the saved file.
        """
        ...

    @abstractmethod
    async def save_from_stream(self, path: str, stream: BinaryIO) -> str:
        """Write a binary stream to the given storage path.

        Useful for large uploads that should not be buffered entirely in memory.

        Args:
            path: Storage path (relative to storage root).
            stream: Open binary stream to read from.

        Returns:
            The full storage path of the saved file.
        """
        ...

    @abstractmethod
    async def read(self, path: str) -> bytes:
        """Read all bytes from a storage path.

        Args:
            path: Storage path (relative to storage root).

        Returns:
            File content as bytes.

        Raises:
            StorageFileNotFound: If the path does not exist.
        """
        ...

    @abstractmethod
    async def read_text(self, path: str, encoding: str = "utf-8") -> str:
        """Read text content from a storage path.

        Args:
            path: Storage path (relative to storage root).
            encoding: Text encoding (default utf-8).

        Returns:
            File content as a string.
        """
        ...

    @abstractmethod
    async def delete(self, path: str) -> None:
        """Delete a file at the given storage path.

        Does not raise if the file does not exist (idempotent).

        Args:
            path: Storage path (relative to storage root).
        """
        ...

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """Check whether a file exists at the given storage path.

        Args:
            path: Storage path (relative to storage root).

        Returns:
            True if the file exists.
        """
        ...

    @abstractmethod
    async def move(self, source: str, destination: str) -> str:
        """Move or rename a file within the storage backend.

        Args:
            source: Current storage path.
            destination: Target storage path.

        Returns:
            The destination path.
        """
        ...

    @abstractmethod
    async def copy(self, source: str, destination: str) -> str:
        """Copy a file within the storage backend.

        Args:
            source: Source storage path.
            destination: Target storage path.

        Returns:
            The destination path.
        """
        ...

    @abstractmethod
    async def create_directory(self, path: str) -> None:
        """Ensure a directory/prefix exists.

        Idempotent — does not raise if already exists.

        Args:
            path: Directory path (relative to storage root).
        """
        ...

    @abstractmethod
    async def list(self, prefix: str) -> list[StorageFileInfo]:
        """List files under a given prefix.

        Args:
            prefix: Storage prefix to list (e.g. "documents/" or "images/abc/").

        Returns:
            List of file info objects.
        """
        ...

    @abstractmethod
    async def size(self, path: str) -> int:
        """Get the size of a file in bytes.

        Args:
            path: Storage path.

        Returns:
            File size in bytes.
        """
        ...

    @abstractmethod
    async def checksum(self, path: str) -> str:
        """Compute the SHA-256 checksum of a file.

        Args:
            path: Storage path.

        Returns:
            Hexadecimal SHA-256 digest.
        """
        ...

    @abstractmethod
    async def cleanup(self, path: str) -> None:
        """Recursively delete a file or directory.

        Args:
            path: Storage path to remove.
        """
        ...

    @abstractmethod
    async def generate_temp_path(self, filename: str) -> str:
        """Generate a unique temporary storage path for an in-progress upload.

        Args:
            filename: Original filename (used to derive extension).

        Returns:
            A unique storage path under the temp directory.
        """
        ...

    @abstractmethod
    async def generate_storage_path(
        self,
        prefix: str,
        document_id: str,
        filename: str = "",
    ) -> str:
        """Generate a permanent storage path for a document or derived artifact.

        Args:
            prefix: Category prefix (e.g. "documents", "images").
            document_id: UUID of the document.
            filename: Optional filename to append.

        Returns:
            A deterministic storage path for the document.
        """
        ...

    @abstractmethod
    def rename(self, source: str, destination: str) -> str:
        """Rename a file within the same directory.

        Args:
            source: Current storage path.
            destination: New storage path (same directory).

        Returns:
            The new storage path.
        """
        ...

    @abstractmethod
    def get_local_path(self, path: str) -> str:
        """Return a local filesystem path for the given storage path.

        For LocalStorageProvider this is the real path. For remote providers
        (S3, Azure, GCS) it downloads the file to a temp directory first and
        returns the temp path.

        This is required because third-party extraction libraries (pypdf,
        python-docx, pdfplumber, pytesseract, etc.) expect local file paths.

        Raises:
            StorageUnavailable: If the file cannot be made available locally.
        """
        ...

    async def close(self) -> None:
        """Clean up storage provider resources on shutdown.

        Override in subclasses that need cleanup (e.g. closing connections,
        deleting temp directories). Default implementation is a no-op.
        """
        ...
