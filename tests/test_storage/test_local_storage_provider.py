"""Comprehensive tests for LocalStorageProvider.

Covers all 18 StorageProvider methods plus path traversal protection,
error handling, and concurrent access safety.
"""

import hashlib
from pathlib import Path

import pytest

from app.storage.exceptions import (
    StorageFileNotFound,
    StoragePermissionDenied,
)
from app.storage.local import LocalStorageProvider


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorageProvider:
    """Create a LocalStorageProvider with a temp root directory."""
    return LocalStorageProvider(
        root_path=str(tmp_path / "root"),
        temp_path=str(tmp_path / "temp"),
    )


@pytest.fixture
def sample_content() -> bytes:
    return b"Hello, Enterprise RAG Platform!"


class TestLocalStorageProvider:
    """Test every method on LocalStorageProvider."""

    # ── save / read ────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_save_and_read(self, storage: LocalStorageProvider) -> None:
        path = "test/hello.txt"
        content = b"Hello, World!"
        saved = await storage.save(path, content)
        assert saved.endswith("test/hello.txt")

        read_back = await storage.read(path)
        assert read_back == content

    @pytest.mark.asyncio
    async def test_read_nonexistent(self, storage: LocalStorageProvider) -> None:
        with pytest.raises(StorageFileNotFound):
            await storage.read("nonexistent/file.txt")

    # ── read_text ──────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_read_text(self, storage: LocalStorageProvider) -> None:
        content = "Hello, 世界!"
        await storage.save("hello.txt", content.encode("utf-8"))
        text = await storage.read_text("hello.txt")
        assert text == content

    @pytest.mark.asyncio
    async def test_read_text_nonexistent(self, storage: LocalStorageProvider) -> None:
        with pytest.raises(StorageFileNotFound):
            await storage.read_text("missing.txt")

    # ── delete ─────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_delete(self, storage: LocalStorageProvider) -> None:
        await storage.save("delete_me.txt", b"delete")
        assert await storage.exists("delete_me.txt")
        await storage.delete("delete_me.txt")
        assert not await storage.exists("delete_me.txt")

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, storage: LocalStorageProvider) -> None:
        await storage.delete("already_gone.txt")  # Should not raise

    # ── exists ─────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_exists(self, storage: LocalStorageProvider) -> None:
        assert not await storage.exists("nothing.txt")
        await storage.save("exists.txt", b"yes")
        assert await storage.exists("exists.txt")

    # ── move ───────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_move(self, storage: LocalStorageProvider) -> None:
        await storage.save("source.txt", b"move me")
        await storage.move("source.txt", "dest.txt")
        assert not await storage.exists("source.txt")
        assert await storage.exists("dest.txt")
        content = await storage.read("dest.txt")
        assert content == b"move me"

    # ── copy ───────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_copy(self, storage: LocalStorageProvider) -> None:
        await storage.save("original.txt", b"copy me")
        await storage.copy("original.txt", "duplicate.txt")
        assert await storage.exists("original.txt")
        assert await storage.exists("duplicate.txt")
        content = await storage.read("duplicate.txt")
        assert content == b"copy me"

    # ── rename ─────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_rename(self, storage: LocalStorageProvider) -> None:
        await storage.save("old_name.txt", b"rename me")
        await storage.rename("old_name.txt", "new_name.txt")
        assert not await storage.exists("old_name.txt")
        assert await storage.exists("new_name.txt")

    @pytest.mark.asyncio
    async def test_rename_nonexistent(self, storage: LocalStorageProvider) -> None:
        from app.storage.exceptions import StorageFileNotFound

        with pytest.raises(StorageFileNotFound):
            await storage.rename("ghost.txt", "nowhere.txt")

    # ── create_directory / list ────────────────────────────

    @pytest.mark.asyncio
    async def test_create_directory_and_list(self, storage: LocalStorageProvider) -> None:
        await storage.create_directory("subdir/nested")
        await storage.save("subdir/nested/file1.txt", b"one")
        await storage.save("subdir/nested/file2.txt", b"two")

        files = await storage.list("subdir/nested")
        paths = {f.path for f in files}
        assert "subdir/nested/file1.txt" in paths
        assert "subdir/nested/file2.txt" in paths

    @pytest.mark.asyncio
    async def test_list_empty_prefix(self, storage: LocalStorageProvider) -> None:
        files = await storage.list("empty_dir")
        assert files == []

    # ── size ───────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_size(self, storage: LocalStorageProvider) -> None:
        content = b"12345"
        await storage.save("size_test.txt", content)
        file_size = await storage.size("size_test.txt")
        assert file_size == 5

    @pytest.mark.asyncio
    async def test_size_nonexistent(self, storage: LocalStorageProvider) -> None:
        with pytest.raises(StorageFileNotFound):
            await storage.size("ghost.txt")

    # ── checksum ───────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_checksum(self, storage: LocalStorageProvider) -> None:
        content = b"checksum me"
        await storage.save("checksum_test.txt", content)
        cksum = await storage.checksum("checksum_test.txt")
        expected = hashlib.sha256(content).hexdigest()
        assert cksum == expected

    @pytest.mark.asyncio
    async def test_checksum_nonexistent(self, storage: LocalStorageProvider) -> None:
        with pytest.raises(StorageFileNotFound):
            await storage.checksum("ghost.txt")

    # ── cleanup ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_cleanup_file(self, storage: LocalStorageProvider) -> None:
        await storage.save("cleanup.txt", b"bye")
        assert await storage.exists("cleanup.txt")
        await storage.cleanup("cleanup.txt")
        assert not await storage.exists("cleanup.txt")

    @pytest.mark.asyncio
    async def test_cleanup_directory(self, storage: LocalStorageProvider) -> None:
        await storage.create_directory("dir_to_clean")
        await storage.save("dir_to_clean/a.txt", b"a")
        await storage.save("dir_to_clean/b.txt", b"b")
        await storage.cleanup("dir_to_clean")
        assert not await storage.exists("dir_to_clean/a.txt")
        assert not await storage.exists("dir_to_clean/b.txt")

    @pytest.mark.asyncio
    async def test_cleanup_nonexistent(self, storage: LocalStorageProvider) -> None:
        await storage.cleanup("does_not_exist")  # Should not raise

    # ── generate_temp_path ─────────────────────────────────

    @pytest.mark.asyncio
    async def test_generate_temp_path(self, storage: LocalStorageProvider) -> None:
        path = await storage.generate_temp_path("myfile.pdf")
        assert "myfile.pdf" in path
        assert await storage.exists(path) is False  # Path generated, file not created

    # ── generate_storage_path ──────────────────────────────

    @pytest.mark.asyncio
    async def test_generate_storage_path(self, storage: LocalStorageProvider) -> None:
        path = await storage.generate_storage_path("documents", "abc-123")
        assert "documents/abc-123" in path

    @pytest.mark.asyncio
    async def test_generate_storage_path_with_filename(self, storage: LocalStorageProvider) -> None:
        path = await storage.generate_storage_path("images", "abc-123", "page1.png")
        assert "images/abc-123/page1.png" in path

    # ── get_local_path ─────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_local_path(self, storage: LocalStorageProvider) -> None:
        await storage.save("local.txt", b"data")
        local = storage.get_local_path("local.txt")
        assert Path(local).exists()
        assert Path(local).read_bytes() == b"data"

    # ── path traversal protection ──────────────────────────

    @pytest.mark.asyncio
    async def test_path_traversal_save(self, storage: LocalStorageProvider) -> None:
        with pytest.raises(StoragePermissionDenied):
            await storage.save("../../etc/passwd", b"evil")

    @pytest.mark.asyncio
    async def test_path_traversal_read(self, storage: LocalStorageProvider) -> None:
        with pytest.raises(StoragePermissionDenied):
            await storage.read("../../../etc/shadow")

    # ── concurrent access ──────────────────────────────────

    @pytest.mark.asyncio
    async def test_concurrent_save_and_read(self, storage: LocalStorageProvider) -> None:
        import asyncio

        async def writer() -> None:
            for i in range(20):
                await storage.save(f"concurrent/file_{i}.txt", f"content_{i}".encode())

        async def reader() -> None:
            for i in range(20):
                if await storage.exists(f"concurrent/file_{i}.txt"):
                    await storage.read(f"concurrent/file_{i}.txt")

        await asyncio.gather(writer(), reader())
        assert await storage.exists("concurrent/file_19.txt")

    # ── close lifecycle ────────────────────────────────────

    @pytest.mark.asyncio
    async def test_close(self, storage: LocalStorageProvider) -> None:
        await storage.save("persist.txt", b"data")
        await storage.close()
        # After close, temp directory is cleaned but root files remain
        exists = await storage.exists("persist.txt")
        assert exists
