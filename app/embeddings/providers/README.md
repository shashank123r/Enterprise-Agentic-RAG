# Embedding Provider Architecture

## Overview

The embedding provider layer abstracts access to embedding model APIs behind a clean interface (`EmbeddingProvider`). Business logic depends only on this interface — never on concrete implementations. This allows switching providers (NVIDIA NIM, OpenAI, Cohere, etc.) via configuration without code changes.

## Architecture

```
┌─────────────────────────────┐
│     IndexingService         │  ← Business logic depends ONLY on interface
│   (not yet implemented)     │
└──────────────┬──────────────┘
               │ depends on
               ▼
┌─────────────────────────────┐
│     EmbeddingProvider       │  ← Abstract interface (ABC)
│                             │
│  + embed_documents()        │
│  + embed_query()            │
│  + batch_embed()            │
│  + health_check()           │
│  + model_info()             │
│  + dimension()              │
│  + close()                  │
└──────────────┬──────────────┘
               │ implements
               ▼
┌─────────────────────────────┐
│ NvidiaNIMEmbeddingProvider  │  ← Concrete implementation
│                             │
│  - httpx.AsyncClient        │
│  - Exponential backoff      │
│  - 15-point validation      │
│  - Connection pooling       │
└─────────────────────────────┘
```

## Embedding Request Lifecycle

```
Client calls embed_documents(texts)
        │
        ▼
Validate inputs (empty, oversized, etc.)
        │
        ▼
batch_embed() splits into batches (configurable batch_size)
        │
        ▼
For each batch:
  ┌──────────────────────────────────────────────┐
  │ _process_single_batch()                      │
  │   │                                          │
  │   ▼                                          │
  │ _retry_with_backoff()                        │
  │   │   ┌─ EmbeddingTimeout    → retry ✓       │
  │   │   ├─ EmbeddingServiceUnavail. → retry ✓  │
  │   │   ├─ EmbeddingAuthError    → NO retry ✗  │
  │   │   └─ EmbeddingError (other) → NO retry ✗ │
  │   ▼                                          │
  │ _call_embedding_api()                        │
  │   │   → POST /embeddings                     │
  │   ▼                                          │
  │ Parse response (OpenAI-compatible format)    │
  │   ▼                                          │
  │ Validate batch response (count, dimensions)  │
  │   ▼                                          │
  │ Validate each vector (NaN, Inf, dim)         │
  │   ▼                                          │
  │ Check for duplicate embeddings              │
  └──────────────────────────────────────────────┘
        │
        ▼
Return BatchEmbeddingResult (vectors + failure tracking)
```

## Retry Policy

| Exception | Retry? | Strategy | Cap |
|---|---|---|---|
| `EmbeddingTimeout` | ✅ Yes | Exponential backoff + random jitter (0-20%) | 30s |
| `EmbeddingServiceUnavailable` | ✅ Yes | Exponential backoff + random jitter | 30s |
| `EmbeddingAuthError` | ❌ No | Immediate failure | - |
| `EmbeddingError` (rate_limited) | ✅ Yes | 2x backoff + random jitter, max 60s | 60s |
| `EmbeddingError` (other) | ❌ No | Immediate failure | - |

## Configuration

All configuration via `.env` / environment variables:

| Variable | Default | Description |
|---|---|---|
| `EMBEDDING_PROVIDER` | `nvidia_nim` | Provider type |
| `NVIDIA_NIM_URL` | `http://localhost:8000` | NIM endpoint base URL |
| `NVIDIA_NIM_API_KEY` | `` | API key for NIM authentication |
| `EMBEDDING_MODEL` | `nvidia/nv-embed-qa-4` | Model name |
| `EMBEDDING_BATCH_SIZE` | `32` | Texts per API call |
| `EMBEDDING_MAX_RETRIES` | `3` | Max retry attempts |
| `EMBEDDING_BACKOFF_MULTIPLIER` | `2.0` | Exponential backoff multiplier |
| `MAX_CONCURRENT_REQUESTS` | `10` | Max parallel API calls |
| `REQUEST_TIMEOUT` | `30` | Request timeout in seconds |

## Adding a New Provider

1. Create a new class implementing `EmbeddingProvider` in `app/embeddings/providers/`
2. Add the provider type to `factory.py`
3. Add any new config variables to `app/core/config.py`

### Example stub:

```python
from app.embeddings.providers.base import EmbeddingProvider

class OpenAIEmbeddingProvider(EmbeddingProvider):
    # Implement all 10 abstract methods
    ...
```

Then register in `factory.py`:

```python
elif provider_type == "openai":
    _provider = OpenAIEmbeddingProvider(...)
```

## Validation Rules

The NVIDIA NIM provider performs 15 validation checks:

| # | Check | Location | Action |
|---|---|---|---|
| 1 | Empty input list | `_validate_inputs` | Raise |
| 2 | Metadata length mismatch | `_validate_inputs` | Raise |
| 3 | Non-string text | `_validate_inputs` | Raise |
| 4 | Empty/whitespace text | `_validate_inputs` | Raise |
| 5 | Oversized text | `_validate_inputs` | Raise |
| 6 | Duplicate input texts | `_validate_inputs` | Log warning |
| 7 | Empty response vectors | `_validate_batch_response` | Raise |
| 8 | Batch count mismatch | `_validate_batch_response` | Raise |
| 9 | Token count mismatch | `_validate_batch_response` | Raise |
| 10 | Inconsistent dimensions | `_validate_batch_response` | Raise |
| 11 | Empty vector | `_validate_vector` | Raise |
| 12 | Dimension mismatch | `_validate_vector` | Raise |
| 13 | NaN values | `_validate_vector` | Raise |
| 14 | Inf values | `_validate_vector` | Raise |
| 15 | Duplicate vectors | `_validate_no_duplicates` | Log warning |
