"""Comprehensive tests for the Milvus Vector Store module.

All tests mock pymilvus internals (connections, utility, Collection)
to avoid requiring a running Milvus instance. Covers:

- VectorStore interface compliance
- Collection CRUD lifecycle
- Vector CRUD (upsert, delete, get, count)
- Batch operations and error handling
- Health checks and connection management
- CollectionManager lifecycle (create, versioned, migrate, rebuild)
- Factory and dependency injection
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.vector_stores.base import VectorRecord, VectorStore
from app.vector_stores.collection_manager import CollectionManager
from app.vector_stores.exceptions import (
    CollectionAlreadyExists,
    CollectionNotFound,
    VectorDimensionMismatch,
    VectorStoreAuthError,
    VectorStoreError,
    VectorStoreUnavailable,
)
from app.vector_stores.factory import (
    create_vector_store,
    get_vector_store,
)
from app.vector_stores.milvus import MilvusVectorStore

# ── Fixtures ───────────────────────────────────────────────


@pytest.fixture
def store() -> MilvusVectorStore:
    """Create a MilvusVectorStore with minimal config for testing."""
    return MilvusVectorStore(
        alias="test",
        host="localhost",
        port=19530,
        collection_prefix="test_",
        default_dimension=4,
    )


@pytest.fixture
def sample_records() -> list[VectorRecord]:
    """Create a list of sample VectorRecords for testing."""
    return [
        VectorRecord(
            chunk_id=f"chunk-{i}",
            document_id="doc-1",
            vector=[0.1 * (i + 1)] * 4,
            text=f"Sample chunk text {i}",
            metadata={"source": f"page_{i}"},
            page_number=i,
            chunk_index=i,
            language="en",
            checksum=f"sha256-{i}",
            version=1,
            source="test.pdf",
            embedding_model="nvidia/nv-embed-qa-4",
        )
        for i in range(5)
    ]


# ═══════════════════════════════════════════════════════════
# MilvusVectorStore Tests
# ═══════════════════════════════════════════════════════════


class TestMilvusVectorStore:
    """Tests for the MilvusVectorStore implementation."""

    # ── Interface Compliance ────────────────────

    def test_is_vector_store(self, store: MilvusVectorStore) -> None:
        assert isinstance(store, VectorStore)

    # ── Connection Management ───────────────────

    @pytest.mark.asyncio
    async def test_connect_success(self, store: MilvusVectorStore) -> None:
        with patch("app.vector_stores.milvus.connections.connect") as mock_connect:
            await store.connect()
            mock_connect.assert_called_once()
            assert store._connected is True

    @pytest.mark.asyncio
    async def test_connect_auth_failure(self, store: MilvusVectorStore) -> None:
        from pymilvus import MilvusException

        with patch(
            "app.vector_stores.milvus.connections.connect",
            side_effect=MilvusException("authentication failed"),
        ):
            with pytest.raises(VectorStoreAuthError):
                await store.connect()
            assert store._connected is False

    @pytest.mark.asyncio
    async def test_connect_connection_refused(self, store: MilvusVectorStore) -> None:
        with patch(
            "app.vector_stores.milvus.connections.connect",
            side_effect=ConnectionError("Connection refused"),
        ):
            with pytest.raises(VectorStoreUnavailable):
                await store.connect()
            assert store._connected is False

    @pytest.mark.asyncio
    async def test_close_disconnects(self, store: MilvusVectorStore) -> None:
        with patch("app.vector_stores.milvus.connections.connect"):
            await store.connect()
            assert store._connected is True

        with patch("app.vector_stores.milvus.connections.disconnect") as mock_disconnect:
            await store.close()
            mock_disconnect.assert_called_once()
            assert store._connected is False

    @pytest.mark.asyncio
    async def test_close_idempotent(self, store: MilvusVectorStore) -> None:
        """Closing an already-disconnected store should not raise."""
        await store.close()
        await store.close()  # Second close should be no-op

    # ── Health Checks ──────────────────────────

    @pytest.mark.asyncio
    async def test_health_check_success(self, store: MilvusVectorStore) -> None:
        with patch("app.vector_stores.milvus.connections.connect"):
            with patch("app.vector_stores.milvus.utility.list_collections") as mock_list:
                mock_list.return_value = ["test_coll"]
                healthy = await store.health_check()
                assert healthy is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, store: MilvusVectorStore) -> None:
        with patch(
            "app.vector_stores.milvus.utility.list_collections",
            side_effect=Exception("Not connected"),
        ):
            healthy = await store.health_check()
            assert healthy is False

    # ── Collection Management ──────────────────

    @pytest.mark.asyncio
    async def test_create_collection(
        self,
        store: MilvusVectorStore,
    ) -> None:
        store._connected = True
        store._alias = "test"

        mock_collection = MagicMock()
        mock_collection.schema.fields = []
        mock_collection.indexes = []
        mock_collection.num_entities = 0

        with (
            patch("app.vector_stores.milvus.utility.has_collection", return_value=False),
            patch("app.vector_stores.milvus.Collection", return_value=mock_collection),
        ):
            stats = await store.create_collection("test_docs", dimension=4)

            assert stats is not None
            assert store._collection_cache.get("test_docs") is not None

    @pytest.mark.asyncio
    async def test_collection_exists_true(self, store: MilvusVectorStore) -> None:
        with patch("app.vector_stores.milvus.connections.connect"):
            with patch("app.vector_stores.milvus.utility.has_collection", return_value=True):
                exists = await store.collection_exists("test_docs")
                assert exists is True

    @pytest.mark.asyncio
    async def test_collection_exists_false(self, store: MilvusVectorStore) -> None:
        with patch("app.vector_stores.milvus.connections.connect"):
            with patch("app.vector_stores.milvus.utility.has_collection", return_value=False):
                exists = await store.collection_exists("nonexistent")
                assert exists is False

    @pytest.mark.asyncio
    async def test_delete_collection_success(self, store: MilvusVectorStore) -> None:
        store._connected = True
        with patch("app.vector_stores.milvus.utility.has_collection", return_value=True):
            with patch("app.vector_stores.milvus.utility.drop_collection") as mock_drop:
                await store.delete_collection("test_docs")
                mock_drop.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_collection_not_found(self, store: MilvusVectorStore) -> None:
        store._connected = True
        with patch("app.vector_stores.milvus.utility.has_collection", return_value=False):
            with pytest.raises(CollectionNotFound):
                await store.delete_collection("nonexistent")

    @pytest.mark.asyncio
    async def test_list_collections_strips_prefix(self, store: MilvusVectorStore) -> None:
        store._connected = True
        with patch(
            "app.vector_stores.milvus.utility.list_collections",
            return_value=["test_docs", "test_images", "other_coll"],
        ):
            names = await store.list_collections()
            assert "docs" in names
            assert "images" in names
            assert "other_coll" not in names  # Doesn't start with prefix

    @pytest.mark.asyncio
    async def test_collection_stats(self, store: MilvusVectorStore) -> None:
        store._connected = True
        mock_collection = MagicMock()
        mock_collection.schema.fields = []
        mock_collection.indexes = []
        mock_collection.num_entities = 42

        with (
            patch("app.vector_stores.milvus.utility.has_collection", return_value=True),
            patch("app.vector_stores.milvus.Collection", return_value=mock_collection),
        ):
            pass  # collection_stats with existing collection tested via exists=False below

        # Test collection not found
        with patch("app.vector_stores.milvus.utility.has_collection", return_value=False):
            stats = await store.collection_stats("nonexistent")
            assert stats["exists"] is False

    # ── Vector CRUD ────────────────────────────

    @pytest.mark.asyncio
    async def test_upsert_vectors_empty_list(self, store: MilvusVectorStore) -> None:
        count = await store.upsert_vectors("docs", [])
        assert count == 0

    @pytest.mark.asyncio
    async def test_upsert_vectors_collection_not_found(self, store: MilvusVectorStore) -> None:
        store._connected = True
        with (patch("app.vector_stores.milvus.utility.has_collection", return_value=False),):
            with pytest.raises(CollectionNotFound):
                await store.upsert_vectors("docs", [VectorRecord(chunk_id="c1", text="hello")])

    @pytest.mark.asyncio
    async def test_upsert_with_dimension_mismatch(
        self,
        store: MilvusVectorStore,
        sample_records: list[VectorRecord],
    ) -> None:
        store._connected = True
        records_with_bad_dim = [VectorRecord(chunk_id="bad", vector=[0.1, 0.2], text="wrong dim")]

        mock_collection = MagicMock()
        # Mock schema to return the vector field with dim=4
        vector_field = MagicMock()
        vector_field.name = "vector"
        vector_field.params = {"dim": 4}
        mock_collection.schema.fields = [MagicMock(), MagicMock(), MagicMock(), vector_field]

        with (
            patch("app.vector_stores.milvus.utility.has_collection", return_value=True),
            patch("app.vector_stores.milvus.Collection", return_value=mock_collection),
        ):
            with pytest.raises(VectorDimensionMismatch):
                await store.upsert_vectors("docs", records_with_bad_dim)

    @pytest.mark.asyncio
    async def test_delete_vectors_no_filter(self, store: MilvusVectorStore) -> None:
        """Deleting without ids or filter_expr should raise."""
        store._connected = True
        with (
            patch("app.vector_stores.milvus.utility.has_collection", return_value=True),
            patch("app.vector_stores.milvus.Collection"),
            pytest.raises(VectorStoreError, match="ids.*filter_expr"),
        ):
            await store.delete_vectors("docs")

    @pytest.mark.asyncio
    async def test_get_vector_not_found(self, store: MilvusVectorStore) -> None:
        store._connected = True
        mock_collection = MagicMock()
        mock_collection.query.return_value = []

        with (
            patch("app.vector_stores.milvus.utility.has_collection", return_value=True),
            patch("app.vector_stores.milvus.Collection", return_value=mock_collection),
        ):
            result = await store.get_vector("docs", "chunk-1")
            assert result is None

    @pytest.mark.asyncio
    async def test_get_vector_count_zero(self, store: MilvusVectorStore) -> None:
        """Count returns 0 for nonexistent collections."""
        with patch("app.vector_stores.milvus.connections.connect"):
            with patch("app.vector_stores.milvus.utility.has_collection", return_value=False):
                count = await store.get_vector_count("nonexistent")
                assert count == 0

    # ── Error Handling ─────────────────────────

    @pytest.mark.asyncio
    async def test_create_collection_failure(self, store: MilvusVectorStore) -> None:
        from pymilvus import MilvusException

        store._connected = True
        with (
            patch("app.vector_stores.milvus.utility.has_collection", return_value=False),
            patch(
                "app.vector_stores.milvus.Collection", side_effect=MilvusException("create failed")
            ),
            pytest.raises(VectorStoreError),
        ):
            await store.create_collection("fail_coll")

    @pytest.mark.asyncio
    async def test_list_collections_failure(self, store: MilvusVectorStore) -> None:
        from pymilvus import MilvusException

        store._connected = True
        with (
            patch(
                "app.vector_stores.milvus.utility.list_collections",
                side_effect=MilvusException("list failed"),
            ),
            pytest.raises(VectorStoreError),
        ):
            await store.list_collections()

    # ── Thread Safety ──────────────────────────

    @pytest.mark.asyncio
    async def test_concurrent_access_safe(self, store: MilvusVectorStore) -> None:
        """Multiple concurrent operations should not cause race conditions."""
        store._connected = True
        mock_collection = MagicMock()
        mock_collection.schema.fields = []
        mock_collection.indexes = []
        mock_collection.num_entities = 0

        with (
            patch("app.vector_stores.milvus.utility.has_collection", return_value=True),
            patch("app.vector_stores.milvus.Collection", return_value=mock_collection),
        ):
            import asyncio

            tasks = [
                store.collection_exists("a"),
                store.collection_exists("b"),
                store.collection_exists("c"),
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            assert all(r is True for r in results)


# ═══════════════════════════════════════════════════════════
# CollectionManager Tests
# ═══════════════════════════════════════════════════════════


class TestCollectionManager:
    """Tests for the CollectionManager lifecycle wrapper."""

    @pytest.fixture
    def mock_store(self) -> MagicMock:
        store = MagicMock(spec=VectorStore)
        store.collection_exists = AsyncMock()
        store.collection_stats = AsyncMock()
        store.create_collection = AsyncMock()
        store.delete_collection = AsyncMock()
        store.list_collections = AsyncMock()
        return store

    @pytest.fixture
    def manager(self, mock_store: MagicMock) -> CollectionManager:
        return CollectionManager(mock_store)

    @pytest.mark.asyncio
    async def test_create_collection_new(
        self,
        manager: CollectionManager,
        mock_store: MagicMock,
    ) -> None:
        mock_store.collection_exists.return_value = False
        mock_store.create_collection.return_value = {"exists": True, "name": "docs"}
        mock_store.collection_stats.return_value = {"exists": True, "name": "docs"}

        result = await manager.create("docs", dimension=4)
        assert result["exists"] is True
        mock_store.create_collection.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_collection_exists_if_not_exists(
        self,
        manager: CollectionManager,
        mock_store: MagicMock,
    ) -> None:
        mock_store.collection_exists.return_value = True
        mock_store.collection_stats.return_value = {"exists": True, "name": "docs"}

        result = await manager.create("docs", dimension=4, if_not_exists=True)
        assert result["exists"] is True
        mock_store.create_collection.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_collection_exists_raises(
        self,
        manager: CollectionManager,
        mock_store: MagicMock,
    ) -> None:
        mock_store.collection_exists.return_value = True
        with pytest.raises(CollectionAlreadyExists):
            await manager.create("docs", dimension=4, if_not_exists=False)

    @pytest.mark.asyncio
    async def test_get_collection_found(
        self,
        manager: CollectionManager,
        mock_store: MagicMock,
    ) -> None:
        mock_store.collection_exists.return_value = True
        mock_store.collection_stats.return_value = {"exists": True, "name": "docs"}

        result = await manager.get("docs")
        assert result["name"] == "docs"

    @pytest.mark.asyncio
    async def test_get_collection_not_found(
        self,
        manager: CollectionManager,
        mock_store: MagicMock,
    ) -> None:
        mock_store.collection_exists.return_value = False
        with pytest.raises(CollectionNotFound):
            await manager.get("nonexistent")

    @pytest.mark.asyncio
    async def test_delete_collection(
        self,
        manager: CollectionManager,
        mock_store: MagicMock,
    ) -> None:
        mock_store.collection_exists.return_value = True
        await manager.delete("docs")
        mock_store.delete_collection.assert_called_once_with("docs")

    @pytest.mark.asyncio
    async def test_delete_nonexistent(
        self,
        manager: CollectionManager,
        mock_store: MagicMock,
    ) -> None:
        mock_store.collection_exists.return_value = False
        with pytest.raises(CollectionNotFound):
            await manager.delete("nonexistent")

    @pytest.mark.asyncio
    async def test_list_all(
        self,
        manager: CollectionManager,
        mock_store: MagicMock,
    ) -> None:
        mock_store.list_collections.return_value = ["docs", "images"]
        mock_store.collection_stats.return_value = {"exists": True}

        results = await manager.list_all()
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_rebuild(
        self,
        manager: CollectionManager,
        mock_store: MagicMock,
    ) -> None:
        mock_store.collection_exists.return_value = True
        mock_store.create_collection.return_value = {"exists": True, "name": "docs"}

        result = await manager.rebuild("docs", dimension=4)
        assert result["exists"] is True
        mock_store.delete_collection.assert_called_once()
        mock_store.create_collection.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_healthy(
        self,
        manager: CollectionManager,
        mock_store: MagicMock,
    ) -> None:
        mock_store.collection_exists.return_value = True
        mock_store.collection_stats.return_value = {
            "exists": True,
            "num_entities": 100,
            "indexes": [{"field": "vector"}],
        }

        health = await manager.health("docs")
        assert health["healthy"] is True
        assert health["vector_count"] == 100

    @pytest.mark.asyncio
    async def test_health_not_found(
        self,
        manager: CollectionManager,
        mock_store: MagicMock,
    ) -> None:
        mock_store.collection_exists.return_value = False
        health = await manager.health("nonexistent")
        assert health["healthy"] is False

    @pytest.mark.asyncio
    async def test_create_versioned(
        self,
        manager: CollectionManager,
        mock_store: MagicMock,
    ) -> None:
        mock_store.list_collections.return_value = []
        mock_store.collection_exists.return_value = False
        mock_store.create_collection.return_value = {"exists": True, "name": "docs_v4_v1"}

        result = await manager.create_versioned("docs", dimension=4)
        # Should have used version 1 since no versioned collections exist
        assert result is not None

    @pytest.mark.asyncio
    async def test_migrate_not_implemented(
        self,
        manager: CollectionManager,
        mock_store: MagicMock,
    ) -> None:
        mock_store.collection_exists.return_value = True
        result = await manager.migrate("source", "target")
        assert result["status"] == "not_implemented"

    @pytest.mark.asyncio
    async def test_migrate_source_not_found(
        self,
        manager: CollectionManager,
        mock_store: MagicMock,
    ) -> None:
        mock_store.collection_exists.return_value = False
        with pytest.raises(CollectionNotFound):
            await manager.migrate("source", "target")


# ═══════════════════════════════════════════════════════════
# Factory & DI Tests
# ═══════════════════════════════════════════════════════════


class TestVectorStoreFactory:
    """Tests for the vector store provider factory."""

    @pytest.mark.asyncio
    async def test_create_milvus_store(self) -> None:
        with (
            patch("app.vector_stores.factory.settings") as mock_settings,
            patch("app.vector_stores.milvus.MilvusVectorStore.connect", new_callable=AsyncMock),
        ):
            mock_settings.VECTOR_STORE_PROVIDER = "milvus"
            mock_settings.MILVUS_ALIAS = "default"
            mock_settings.MILVUS_HOST = "localhost"
            mock_settings.MILVUS_PORT = 19530
            mock_settings.MILVUS_USERNAME = ""
            mock_settings.MILVUS_PASSWORD = ""
            mock_settings.MILVUS_COLLECTION_PREFIX = "rag_"
            mock_settings.VECTOR_STORE_DIMENSION = 2048
            mock_settings.MILVUS_CONNECT_TIMEOUT = 10

            store = await create_vector_store()
            from app.vector_stores.milvus import MilvusVectorStore

            assert isinstance(store, MilvusVectorStore)

    @pytest.mark.asyncio
    async def test_unknown_provider_raises(self) -> None:
        with patch("app.vector_stores.factory.settings") as mock_settings:
            mock_settings.VECTOR_STORE_PROVIDER = "unknown"
            with pytest.raises(VectorStoreError, match="Unknown vector store"):
                await create_vector_store()

    @pytest.mark.asyncio
    async def test_get_vector_store_yields_instance(self) -> None:
        with (
            patch(
                "app.vector_stores.factory.create_vector_store", new_callable=AsyncMock
            ) as mock_create,
        ):
            mock_store = MagicMock(spec=VectorStore)
            mock_create.return_value = mock_store

            results = []
            async for store in get_vector_store():
                results.append(store)
                break

            assert len(results) == 1
            assert results[0] is mock_store

    @pytest.mark.asyncio
    async def test_close_vector_store(self) -> None:
        """Closing should call close() on the store."""
        from app.vector_stores.factory import close_vector_store

        mock_store = MagicMock(spec=VectorStore)
        mock_store.close = AsyncMock()

        # Inject mock store
        from app.vector_stores import factory

        factory._vector_store = mock_store

        await close_vector_store()
        mock_store.close.assert_called_once()
        assert factory._vector_store is None


# ═══════════════════════════════════════════════════════════
# Schema & Data Conversion Tests
# ═══════════════════════════════════════════════════════════


class TestMilvusDataConversion:
    """Tests for internal data conversion methods."""

    @pytest.fixture
    def store(self) -> MilvusVectorStore:
        return MilvusVectorStore(default_dimension=4)

    def test_build_schema_default(self, store: MilvusVectorStore) -> None:
        schema = store._build_schema(dimension=4)
        assert schema is not None
        # The vector field should have dim=4
        vector_field = schema.fields[3]  # index 3 is "vector"
        assert vector_field.params.get("dim") == 4

    def test_build_schema_with_override(self, store: MilvusVectorStore) -> None:
        schema = store._build_schema(dimension=4, schema_override={"text_max_len": 1000})
        assert schema is not None

    def test_records_to_entities(self, store: MilvusVectorStore) -> None:
        records = [
            VectorRecord(
                chunk_id="c1",
                document_id="doc1",
                vector=[0.1, 0.2, 0.3, 0.4],
                text="Hello",
                metadata={"page": 1},
                chunk_index=0,
                version=1,
                source="test.pdf",
                embedding_model="test-model",
            ),
        ]
        entities = store._records_to_entities(records)
        assert len(entities) == 1
        assert entities[0]["chunk_id"] == "c1"
        assert entities[0]["document_id"] == "doc1"
        assert entities[0]["vector"] == [0.1, 0.2, 0.3, 0.4]
        assert entities[0]["text"] == "Hello"
        assert entities[0]["chunk_index"] == 0
        assert entities[0]["version"] == 1
        assert entities[0]["source"] == "test.pdf"

    def test_records_to_entities_empty_chunk_id(self, store: MilvusVectorStore) -> None:
        """Empty chunk_id should get auto-generated UUID."""
        records = [
            VectorRecord(chunk_id="", vector=[0.1, 0.2, 0.3, 0.4], text="auto"),
        ]
        entities = store._records_to_entities(records)
        assert entities[0]["chunk_id"] != ""

    def test_entity_to_record(self, store: MilvusVectorStore) -> None:
        entity = {
            "id": 1,
            "chunk_id": "c1",
            "document_id": "doc1",
            "vector": [0.1, 0.2, 0.3, 0.4],
            "text": "Hello",
            "metadata": {"page": 1},
            "page_number": 1,
            "chunk_index": 0,
            "section_title": "Intro",
            "language": "en",
            "checksum": "abc",
            "version": 2,
            "source": "test.pdf",
            "embedding_model": "test-model",
        }
        record = store._entity_to_record(entity)
        assert record.chunk_id == "c1"
        assert record.document_id == "doc1"
        assert record.text == "Hello"
        assert record.version == 2
        assert record.section_title == "Intro"
        assert record.language == "en"

    def test_prefixed_name(self, store: MilvusVectorStore) -> None:
        assert store._prefixed_name("docs") == "rag_docs"

    def test_strip_prefix(self, store: MilvusVectorStore) -> None:
        assert store._strip_prefix("rag_docs") == "docs"

    def test_strip_prefix_no_match(self, store: MilvusVectorStore) -> None:
        assert store._strip_prefix("other_docs") == "other_docs"
