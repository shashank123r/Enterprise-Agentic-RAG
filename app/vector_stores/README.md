# Vector Store Module

Production-grade vector database abstraction for Milvus (and soon Pinecone, Weaviate, Qdrant).

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Business Logic                        │
│      (depends ONLY on VectorStore ABC)                  │
└──────────────────┬──────────────────────────────────────┘
                   │ inject via FastAPI DI
┌──────────────────▼──────────────────────────────────────┐
│                    VectorStore (ABC)                     │
│  ┌──────────────────────────────────────────────────┐   │
│  │  create_collection()  delete_collection()        │   │
│  │  upsert_vectors()     delete_vectors()           │   │
│  │  get_vector()         get_vector_count()         │   │
│  │  collection_stats()   health_check()             │   │
│  │  collection_exists()  list_collections()         │   │
│  │  close()                                          │   │
│  └──────────────────────────────────────────────────┘   │
└──────────────────┬──────────────────────────────────────┘
                   │ implements
┌──────────────────▼──────────────────────────────────────┐
│              MilvusVectorStore                           │
│  ┌──────────────────────────────────────────────────┐   │
│  │  pymilvus (offloaded via ThreadPoolExecutor)     │   │
│  │  Connection pooling │ Retry │ Auth │ Health      │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│              CollectionManager                           │
│  ┌──────────────────────────────────────────────────┐   │
│  │  create()  delete()  rebuild()  migrate()        │   │
│  │  create_versioned()  health()  health_all()      │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## Collection Naming

Collections are created with a configurable prefix (default: `rag_`).

| Pattern | Example | Description |
|---------|---------|-------------|
| `{prefix}{name}` | `rag_docs` | Simple collection |
| `{prefix}{name}_v{dim}_v{version}` | `rag_docs_v4_v1` | Versioned collection |

### Versioned Collections

Versioned collections isolate indexes by embedding dimension and schema version.
This enables safe schema migrations without breaking existing data:

```python
manager = CollectionManager(vector_store)

# Creates "rag_docs_v2048_v1"
info = await manager.create_versioned("docs", dimension=2048)

# Upgrade to new model: creates "rag_docs_v2048_v2"
info2 = await manager.create_versioned("docs", dimension=2048)
```

## Metadata Schema

Every vector in a collection stores the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `id` | INT64 (auto) | Auto-generated primary key |
| `chunk_id` | VARCHAR(64) | Unique chunk UUID |
| `document_id` | VARCHAR(64) | Parent document UUID |
| `vector` | FLOAT_VECTOR(dim) | Embedding vector |
| `text` | VARCHAR(65535) | Chunk text content |
| `metadata` | JSON | Rich metadata |
| `page_number` | INT64 | Source page number |
| `chunk_index` | INT64 | Position within document |
| `section_title` | VARCHAR(256) | Section heading |
| `language` | VARCHAR(16) | Detected language code |
| `checksum` | VARCHAR(64) | SHA-256 content checksum |
| `version` | INT64 | Document version number |
| `source` | VARCHAR(256) | Source filename or URL |
| `embedding_model` | VARCHAR(128) | Embedding model name |

## Configuration (.env)

```bash
# Provider
VECTOR_STORE_PROVIDER=milvus
VECTOR_STORE_DIMENSION=2048

# Milvus Connection
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_ALIAS=default
MILVUS_USERNAME=
MILVUS_PASSWORD=
MILVUS_COLLECTION_PREFIX=rag_
MILVUS_CONNECT_TIMEOUT=10
```

## Index Configuration

Collections use IVF_FLAT indexing with COSINE metric by default:

- **Index type:** IVF_FLAT
- **Metric type:** COSINE
- **nlist:** 1024 (adjust based on collection size)
- **nprobe:** 10 (search parameter)

## Error Handling

All Milvus-specific exceptions are converted to domain exceptions:

| Milvus Exception | Domain Exception | HTTP Status |
|-----------------|-----------------|-------------|
| ConnectionError | `VectorStoreUnavailable` | 503 |
| Auth failure | `VectorStoreAuthError` | 503 |
| Collection not found | `CollectionNotFound` | 404 |
| Dimension mismatch | `VectorDimensionMismatch` | 400 |
| Batch failure | `BatchInsertError` | 500 |
| Timeout | `VectorStoreTimeout` | 503 |

## Dependency Injection

Inject `VectorStore` or `CollectionManager` in FastAPI routes:

```python
from fastapi import APIRouter, Depends
from app.core.dependencies import get_vector_store, get_collection_manager
from app.vector_stores import VectorStore, CollectionManager

router = APIRouter()

@router.post("/collections")
async def create_collection(
    name: str,
    dimension: int = 2048,
    manager: CollectionManager = Depends(get_collection_manager),
):
    return await manager.create(name, dimension=dimension)

@router.post("/collections/{name}/vectors")
async def upsert_vectors(
    name: str,
    vectors: list[VectorRecord],
    store: VectorStore = Depends(get_vector_store),
):
    count = await store.upsert_vectors(name, vectors)
    return {"upserted": count}
```

## Thread Safety

All synchronous `pymilvus` calls are offloaded to a thread executor via
`_run_sync()`. A lock guards connection state. The implementation is
fully safe for concurrent use.

## Extension Guide

To add a new vector database:

1. Create `app/vector_stores/{provider_name}.py`
2. Implement `VectorStore` ABC
3. Add the provider to `factory.py`
4. Add configuration to `app/core/config.py`

### Example: Pinecone Stub

```python
# app/vector_stores/pinecone.py
class PineconeVectorStore(VectorStore):
    async def create_collection(self, name, dimension=None, schema=None):
        ...

    async def upsert_vectors(self, collection_name, vectors, batch_size=100):
        ...

    # ... (all other abstract methods)
```

### Factory Registration

```python
# app/vector_stores/factory.py (add to create_vector_store)
if provider == "pinecone":
    from app.vector_stores.pinecone import PineconeVectorStore
    store = PineconeVectorStore(api_key=..., environment=...)
    return store
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/collections` | Create collection |
| `GET` | `/api/v1/collections` | List collections |
| `GET` | `/api/v1/collections/{name}` | Collection stats |
| `DELETE` | `/api/v1/collections/{name}` | Delete collection |
| `POST` | `/api/v1/collections/{name}/vectors` | Upsert vectors |
| `DELETE` | `/api/v1/collections/{name}/vectors` | Delete vectors |
| `GET` | `/api/v1/collections/{name}/count` | Vector count |
| `GET` | `/api/v1/vector-store/health` | Health check |
| `POST` | `/api/v1/collections/{name}/rebuild` | Rebuild collection |
| `POST` | `/api/v1/collections/{name}/migrate` | Migrate collection |

## Testing

```bash
# Unit tests (mocked — no Milvus required)
pytest tests/test_vector_stores/ -v

# Coverage
pytest tests/test_vector_stores/ --cov=app.vector_stores --cov-report=term-missing
```

## Future Providers (stubs ready)

- **Pinecone** — managed vector DB with auto-scaling
- **Weaviate** — vector + object storage with GraphQL
- **Qdrant** — Rust-based vector DB with rich filtering
- **Milvus** — ✅ Implemented (default)
