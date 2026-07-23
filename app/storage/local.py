"""Local filesystem storage provider — all I/O offloaded via run_in_executor.

This is the default storage backend. It satisfies the StorageProvider
interface so the ingestion pipeline never touches pathlib/shutil directly.
"""

import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from app.core.logging import get_logger
from app.ingestion.executor import run_in_executor
from app.storage.base import StorageProvider
from app.storage.exceptions import (
    StorageFileNotFound,
    StoragePermissionDenied,
    StorageQuotaExceeded,
)
from app.storage.models import StorageFileInfo

logger = get_logger(__name__)


class LocalStorageProvider(StorageProvider):
    """Stores files on the local filesystem.

    All filesystem operations are offloaded to the ingestion thread pool
    via ``run_in_executor`` to keep the asyncio event loop responsive.

    Args:
        root_path: Base directory for all stored files.
        temp_path: Directory for temporary upload files.
    """

    def __init__(self, root_path: str, temp_path: str = "") -> None:
        self._root = Path(root_path).resolve()
        self._temp = Path(temp_path).resolve() if temp_path else self._root / "temp"
        self._root.mkdir(parents=True, exist_ok=True)
        self._temp.mkdir(parents=True, exist_ok=True)

    # ── Path resolution ────────────────────────────────────

    def _resolve(self, path: str) -> Path:
        """Convert a storage path to an absolute filesystem path."""
        # Prevent directory traversal attacks
        clean = Path(path).as_posix().lstrip("/")
        resolved = (self._root / clean).resolve()
        if not str(resolved).startswith(str(self._root)):
            raise StoragePermissionDenied(
                path, f"Path traversal detected: {path}"
            )
        return resolved

    def _resolve_temp(self, path: str) -> Path:
        """Convert a temp storage path to an absolute filesystem path."""
        clean = Path(path).as_posix().lstrip("/")
        resolved = (self._temp / clean).resolve()
        if not str(resolved).startswith(str(self._temp)):
            raise StoragePermissionDenied(
                path, f"Path traversal detected in temp: {path}"
            )
        return resolved

    # ── StorageProvider interface ──────────────────────────

    async def save(self, path: str, content: bytes) -> str:
        resolved = self._resolve(path)

        def _do() -> str:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_bytes(content)
            return str(resolved)

        return await run_in_executor(_do)

    async def save_from_stream(self, path: str, stream: BinaryIO) -> str:
        resolved = self._resolve(path)

        def _do() -> str:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            with open(resolved, "wb") as f:
                shutil.copyfileobj(stream, f)
            return str(resolved)

        return await run_in_executor(_do)

    async def read(self, path: str) -> bytes:
        resolved = self._resolve(path)

        def _do() -> bytes:
            if not resolved.exists():
                raise StorageFileNotFound(path)
            return resolved.read_bytes()

        return await run_in_executor(_do)

    async def read_text(self, path: str, encoding: str = "utf-8") -> str:
        resolved = self._resolve(path)

        def _do() -> str:
            if not resolved.exists():
                raise StorageFileNotFound(path)
            return resolved.read_text(encoding)

        return await run_in_executor(_do)

    async def delete(self, path: str) -> None:
        resolved = self._resolve(path)

        def _do() -> None:
            if resolved.exists():
                resolved.unlink()
                logger.debug("Deleted file", path=str(resolved))

        await run_in_executor(_do)

    async def exists(self, path: str) -> bool:
        resolved = self._resolve(path)

        def _do() -> bool:
            return resolved.exists()

        return await run_in_executor(_do)

    async def move(self, source: str, destination: str) -> str:
        src_resolved = self._resolve(source)
        dst_resolved = self._resolve(destination)

        def _do() -> str:
            dst_resolved.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src_resolved), str(dst_resolved))
            return str(dst_resolved)

        return await run_in_executor(_do)

    async def copy(self, source: str, destination: str) -> str:
        src_resolved = self._resolve(source)
        dst_resolved = self._resolve(destination)

        def _do() -> str:
            dst_resolved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src_resolved), str(dst_resolved))
            return str(dst_resolved)

        return await run_in_executor(_do)

    async def create_directory(self, path: str) -> None:
        resolved = self._resolve(path)

        def _do() -> None:
            resolved.mkdir(parents=True, exist_ok=True)

        await run_in_executor(_do)

    async def list(self, prefix: str) -> list[StorageFileInfo]:
        resolved = self._resolve(prefix)

        def _do() -> list[StorageFileInfo]:
            if not resolved.exists():
                return []
            results: list[StorageFileInfo] = []
            for child in resolved.iterdir():
                stat = child.stat()
                mtime = datetime.fromtimestamp(stat.st_mtime)
                results.append(
                    StorageFileInfo(
                        path=str(child.relative_to(self._root)),
                        size_bytes=stat.st_size,
                        modified_at=mtime,
                        is_directory=child.is_dir(),
                    )
                )
            return results

        return await run_in_executor(_do)

    async def size(self, path: str) -> int:
        resolved = self._resolve(path)

        def _do() -> int:
            if not resolved.exists():
                raise StorageFileNotFound(path)
            return resolved.stat().st_size

        return await run_in_executor(_do)

    async def checksum(self, path: str) -> str:
        resolved = self._resolve(path)

        def _do() -> str:
            if not resolved.exists():
                raise StorageFileNotFound(path)
            sha256 = hashlib.sha256()
            with open(resolved, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    sha256.update(chunk)
            return sha256.hexdigest()

        return await run_in_executor(_do)

    async def cleanup(self, path: str) -> None:
        resolved = self._resolve(path)

        def _do() -> None:
            if not resolved.exists():
                return
            if resolved.is_dir():
                shutil.rmtree(resolved, ignore_errors=True)
            else:
                resolved.unlink(missing_ok=True)
            logger.debug("Cleaned up path", path=str(resolved))

        await run_in_executor(_do)

    async def generate_temp_path(self, filename: str) -> str:
        def _do() -> str:
            self._temp.mkdir(parents=True, exist_ok=True)
            unique = f"{uuid4()}_{filename}"
            return f"temp/{unique}"

        return await run_in_executor(_do)

    async def generate_storage_path(
        self, prefix: str, document_id: str, filename: str = "",
    ) -> str:
        def _do() -> str:
            if filename:
                return f"{prefix}/{document_id}/{filename}"
            return f"{prefix}/{document_id}"

        return await run_in_executor(_do)

    async def rename(self, source: str, destination: str) -> str:
        src_resolved = self._resolve(source)
        dst_resolved = self._resolve(destination)

        def _do() -> str:
            if not src_resolved.exists():
                raise StorageFileNotFound(source)
            dst_resolved.parent.mkdir(parents=True, exist_ok=True)
            src_resolved.rename(dst_resolved)
            return str(dst_resolved)

        return await run_in_executor(_do)

    def get_local_path(self, path: str) -> str:
        """Return the real local filesystem path.

        For LocalStorageProvider this is the actual file path.
        For remote providers this would download to a temp directory.
        """
        return str(self._resolve(path))

    # ── Lifecycle ──────────────────────────────────────────

    async def close(self) -> None:
        """Clean up temporary files on shutdown."""
        if self._temp.exists():
            await self.cleanup(str(self._temp))
