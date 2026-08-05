"""NVIDIA NIM embedding provider.

Implements the EmbeddingProvider interface for NVIDIA NIM endpoints.
Supports async HTTP, configurable batching, retry with exponential backoff
and jitter, comprehensive embedding validation, connection pooling,
and graceful shutdown.
"""

import asyncio
import math
import random
from typing import Any

import httpx
from langdetect import detect as _detect_lang

from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import get_metrics
from app.embeddings.exceptions import (
    DuplicateInputIdError,
    EmbeddingAuthError,
    EmbeddingError,
    EmbeddingServiceUnavailable,
    EmbeddingTimeout,
    UnsupportedLanguageError,
)
from app.embeddings.providers.base import (
    BatchEmbeddingResult,
    EmbeddingProvider,
    EmbeddingProviderInfo,
    EmbeddingResult,
)

logger = get_logger(__name__)

# Model metadata — sourced from NVIDIA NIM docs
_NIM_MODEL_DIMENSIONS: dict[str, int] = {
    "nvidia/nv-embed-qa-4": 2048,
    "nvidia/nv-embed-qa-4-v2": 2048,
    "nvidia/nv-embed-qa-1": 1024,
    "nvidia/nv-embed-v1": 4096,
    "nvidia/nv-embedqa-e5-v5": 1024,
    "nvidia/nv-embedqa-mistral-7b-v2": 384,
    "nvidia/embed-qa-4": 2048,
    "nvidia/llama-3.2-nv-embedqa-1b-v1": 1024,
    "nvidia/llama-nemotron-embed-1b-v2": 1024,
    "snowflake/arctic-embed-l": 1024,
}

_NIM_MODEL_MAX_TOKENS: dict[str, int] = {
    "nvidia/nv-embed-qa-4": 512,
    "nvidia/nv-embed-qa-4-v2": 512,
    "nvidia/nv-embed-qa-1": 512,
    "nvidia/nv-embed-v1": 512,
    "nvidia/nv-embedqa-e5-v5": 512,
    "nvidia/embed-qa-4": 512,
    "nvidia/llama-3.2-nv-embedqa-1b-v1": 512,
    "nvidia/llama-nemotron-embed-1b-v2": 512,
    "snowflake/arctic-embed-l": 512,
}


class NvidiaNIMEmbeddingProvider(EmbeddingProvider):
    """Embedding provider for NVIDIA NIM endpoints.

    Features:
    - httpx.AsyncClient with connection pooling, keep-alive
    - Configurable batch size and concurrency
    - Exponential backoff with jitter (transient failures only)
    - 15-point embedding validation (dimension, NaN, Inf, dedup, etc.)
    - Partial batch isolation — one failed batch never blocks others
    - Comprehensive health check with latency and auth status
    - All exceptions converted to AppException-derived types
    """

    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        batch_size: int | None = None,
        max_concurrent: int | None = None,
        timeout: int | None = None,
        max_retries: int | None = None,
        backoff_multiplier: float | None = None,
    ) -> None:
        self._api_url = (api_url or str(settings.NIM_EMBEDDING_URL)).rstrip("/")
        self._api_key = api_key or settings.NIM_API_KEY
        self._model = model or settings.NIM_MODEL_EMBEDDING
        self._batch_size = batch_size or settings.EMBEDDING_BATCH_SIZE
        self._max_concurrent = max_concurrent or settings.MAX_CONCURRENT_REQUESTS
        self._timeout = timeout or settings.REQUEST_TIMEOUT
        self._max_retries = max_retries or settings.EMBEDDING_MAX_RETRIES
        self._backoff = backoff_multiplier or settings.EMBEDDING_BACKOFF_MULTIPLIER

        self._semaphore = asyncio.Semaphore(self._max_concurrent)
        self._client: httpx.AsyncClient | None = None
        self._dimension: int | None = self._lookup_dimension()
        self._max_tokens: int = self._lookup_max_tokens()
        self._language_validation_enabled: bool = True
        self._supported_langs: list[str] = ["en"]

    # ── HTTP client ───────────────────────────────────────

    @property
    def client(self) -> httpx.AsyncClient:
        """Lazy-initialized HTTP client with connection pooling."""
        if self._client is None:
            headers: dict[str, str] = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Accept-Encoding": "gzip",  # Request compression
            }
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"

            limits = httpx.Limits(
                max_keepalive_connections=self._max_concurrent,
                max_connections=self._max_concurrent * 2,
                keepalive_expiry=30.0,
            )

            self._client = httpx.AsyncClient(
                headers=headers,
                timeout=httpx.Timeout(self._timeout, connect=10.0),
                limits=limits,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client and release connections."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("NVIDIA NIM provider connections closed")

    # ── Core embedding ────────────────────────────────────

    async def embed_documents(
        self,
        texts: list[str],
        metadata: list[dict[str, Any]] | None = None,
    ) -> BatchEmbeddingResult:
        """Embed document texts via NVIDIA NIM."""
        self._validate_inputs(texts, metadata)
        return await self.batch_embed(texts, metadata=metadata)

    async def embed_query(self, text: str) -> EmbeddingResult:
        """Embed a single query string."""
        self._validate_inputs([text], None)
        vectors, token_counts = await self._call_embedding_api([text], input_type="query")
        if not vectors:
            raise EmbeddingError("Empty response from embedding provider", code="empty_embedding")

        self._validate_vector(vectors[0])
        return EmbeddingResult(
            vector=vectors[0],
            text=text,
            token_count=token_counts[0] if token_counts else 0,
            model=self._model,
        )

    async def batch_embed(
        self,
        texts: list[str],
        batch_size: int = 32,
        metadata: list[dict[str, Any]] | None = None,
    ) -> BatchEmbeddingResult:
        """Embed texts with automatic batching and parallel execution.

        Batches are processed concurrently (up to max_concurrent). A failure
        in one batch is isolated — it records failed indices and continues
        with remaining batches.
        """
        self._validate_inputs(texts, metadata)

        if not texts:
            return BatchEmbeddingResult(vectors=[], texts=[], model=self._model)

        actual_batch_size = min(batch_size, self._batch_size)
        all_vectors: list[list[float]] = []
        all_token_counts: list[int] = []
        all_texts: list[str] = []
        failed_indices: list[int] = []
        errors: list[str] = []
        results_lock = asyncio.Lock()

        # Split texts into batches
        batches = [
            texts[i : i + actual_batch_size] for i in range(0, len(texts), actual_batch_size)
        ]

        async def process_batch(
            batch_texts: list[str],
            batch_start_idx: int,
        ) -> None:
            nonlocal all_vectors, all_texts, all_token_counts
            async with self._semaphore:
                batch_result = await self._process_single_batch(
                    batch_texts,
                    batch_start_idx,
                    actual_batch_size,
                )
                async with results_lock:
                    all_vectors.extend(batch_result["vectors"])
                    all_texts.extend(batch_result["texts"])
                    all_token_counts.extend(batch_result["token_counts"])
                    failed_indices.extend(batch_result["failed_indices"])
                    if batch_result.get("error"):
                        errors.append(batch_result["error"])

        # Process batches with concurrency control and cancellation support
        tasks = [process_batch(batch, i * actual_batch_size) for i, batch in enumerate(batches)]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            # Cancel all remaining in-flight tasks and clean up
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            get_metrics().increment("embedding.batch_cancelled", tags={"model": self._model})
            raise  # Preserve cancellation semantics

        return BatchEmbeddingResult(
            vectors=all_vectors,
            texts=all_texts or texts[: len(all_vectors)],
            token_counts=all_token_counts,
            model=self._model,
            failed_indices=sorted(set(failed_indices)),
            errors=errors,
        )

    async def _process_single_batch(
        self,
        batch_texts: list[str],
        batch_start_idx: int,
        batch_size: int,
    ) -> dict[str, Any]:
        """Process a single batch with retry and validation.

        Returns a dict with vectors, texts, token_counts, failed_indices, and
        optional error. This isolates failures to individual batches.
        """
        try:
            vectors, token_counts = await self._retry_with_backoff(
                self._call_embedding_api,
                batch_texts,
                input_type="passage",
            )

            # Validate batch response
            self._validate_batch_response(batch_texts, vectors, token_counts, batch_start_idx)

            # Validate every vector in the batch
            for i, vec in enumerate(vectors):
                self._validate_vector(vec)

            # Check for duplicate embeddings within the batch
            self._validate_no_duplicates(vectors)

            return {
                "vectors": vectors,
                "texts": batch_texts[: len(vectors)],
                "token_counts": token_counts,
                "failed_indices": [],
                "error": None,
            }

        except EmbeddingError as e:
            failed = list(range(batch_start_idx, batch_start_idx + len(batch_texts)))
            get_metrics().increment(
                "embedding.batch_failed", tags={"model": self._model, "error": e.code}
            )
            return {
                "vectors": [],
                "texts": [],
                "token_counts": [],
                "failed_indices": failed,
                "error": f"Batch at {batch_start_idx}: {e.message} (code={e.code})",
            }

    # ── Health and metadata ───────────────────────────────

    async def health_check(self) -> bool:
        """Check if the NIM endpoint is reachable and responding.

        Returns detailed health info in model_info. This probe simply
        verifies the endpoint returns valid embeddings.
        """
        try:
            result = await self._call_embedding_api(["health"], input_type="passage")
            if not result[0] or not result[0][0]:
                return False
            self._validate_vector(result[0][0])
            return True
        except Exception:
            return False

    async def model_info(self) -> EmbeddingProviderInfo:
        """Get metadata about the current model."""
        dim = await self.dimension()
        max_tok = await self.max_input_tokens()

        # Measure health check latency for reporting
        import time

        start = time.monotonic()
        healthy = await self.health_check()
        latency_ms = (time.monotonic() - start) * 1000

        info = EmbeddingProviderInfo(
            provider_name=self.provider_name(),
            model_name=self._model,
            dimension=dim,
            max_input_tokens=max_tok,
            supported_languages=["en"],
            requires_api_key=bool(self._api_key),
        )
        # Attach runtime info to a mutable metadata field
        info.metadata = {  # type: ignore[attr-defined]
            "healthy": healthy,
            "latency_ms": round(latency_ms, 2),
            "auth_configured": bool(self._api_key),
            "api_url": self._api_url,
            "batch_size": self._batch_size,
            "max_concurrent": self._max_concurrent,
        }
        return info

    async def dimension(self) -> int:
        """Get embedding dimension — cached after first call."""
        if self._dimension is not None:
            return self._dimension

        for model_key, dim in _NIM_MODEL_DIMENSIONS.items():
            if model_key in self._model:
                self._dimension = dim
                return dim

        result = await self._call_embedding_api(["test"], input_type="passage")
        if result[0]:
            self._dimension = len(result[0][0])
            return self._dimension
        return 2048

    async def max_input_tokens(self) -> int:
        """Get max input tokens — cached after first call."""
        if self._max_tokens is not None:
            return self._max_tokens

        for model_key, tokens in _NIM_MODEL_MAX_TOKENS.items():
            if model_key in self._model:
                self._max_tokens = tokens
                return tokens
        return 512

    async def supported_languages(self) -> list[str]:
        return ["en"]

    @staticmethod
    def _lookup_max_tokens(model: str | None = None) -> int:
        """Look up max tokens from the static model table."""
        model_name = model or settings.NIM_MODEL_EMBEDDING
        for model_key, tokens in _NIM_MODEL_MAX_TOKENS.items():
            if model_key in model_name:
                return tokens
        return 512

    @staticmethod
    def _lookup_dimension(model: str | None = None) -> int | None:
        """Look up dimension from the static model table."""
        model_name = model or settings.NIM_MODEL_EMBEDDING
        for model_key, dim in _NIM_MODEL_DIMENSIONS.items():
            if model_key in model_name:
                return dim
        return None

    def provider_name(self) -> str:
        return "nvidia_nim"

    # ── Internal API call ─────────────────────────────────

    async def _call_embedding_api(
        self,
        texts: list[str],
        input_type: str = "passage",
    ) -> tuple[list[list[float]], list[int]]:
        """Call the NVIDIA NIM embedding endpoint.

        Returns (vectors, token_counts). All HTTP/network exceptions are
        converted to EmbeddingError subclasses.
        """
        if not texts:
            return [], []

        payload: dict[str, Any] = {
            "input": texts,
            "model": self._model,
            "input_type": input_type,
            "encoding_format": "float",
        }

        try:
            response = await self.client.post(
                f"{self._api_url}/embeddings",
                json=payload,
            )
        except httpx.TimeoutException:
            get_metrics().increment("embedding.timeout", tags={"model": self._model})
            raise EmbeddingTimeout(f"Embedding request timed out after {self._timeout}s")
        except httpx.ConnectError as e:
            get_metrics().increment("embedding.connection_error")
            raise EmbeddingServiceUnavailable(f"Cannot connect to NIM endpoint: {e}")
        except httpx.HTTPError as e:
            get_metrics().increment("embedding.http_error")
            raise EmbeddingServiceUnavailable(f"HTTP error: {e}")

        # HTTP status handling
        if response.status_code == 401 or response.status_code == 403:
            raise EmbeddingAuthError("Authentication failed — check NVIDIA NIM API key")
        if response.status_code == 429:
            get_metrics().increment("embedding.rate_limited")
            raise EmbeddingError("Rate limited by NVIDIA NIM", code="rate_limited")
        if response.status_code >= 500:
            raise EmbeddingServiceUnavailable(f"NIM server error (HTTP {response.status_code})")
        if response.status_code >= 400:
            body = ""
            try:
                body = response.text[:200]
            except Exception:
                pass
            raise EmbeddingError(
                f"NIM returned HTTP {response.status_code}: {body}",
                code="http_error",
            )

        # Parse response
        try:
            data = response.json()
        except Exception as e:
            raise EmbeddingError(f"Invalid JSON response: {e}", code="invalid_response")

        raw_data = data.get("data", data)
        if not isinstance(raw_data, list):
            raise EmbeddingError(
                f"Unexpected response format: {type(raw_data).__name__}",
                code="invalid_response",
            )

        vectors: list[list[float]] = []
        token_counts: list[int] = []
        for item in raw_data:
            embedding = item.get("embedding") or item.get("vector")
            if embedding is None:
                raise EmbeddingError("Missing embedding in response", code="invalid_response")
            vectors.append(list(embedding))
            token_counts.append(item.get("usage", {}).get("prompt_tokens", 0))

        # Top-level usage fallback
        if not token_counts and "usage" in data:
            usage = data["usage"]
            total = usage.get("total_tokens", 0) or usage.get("prompt_tokens", 0)
            per_text = max(1, total // max(len(texts), 1))
            token_counts = [per_text] * len(vectors)

        # Sort by index if present
        if raw_data and isinstance(raw_data[0], dict) and "index" in raw_data[0]:
            indexed = sorted(raw_data, key=lambda x: x.get("index", 0))
            vectors = [list(item.get("embedding") or item.get("vector", [])) for item in indexed]

        get_metrics().increment(
            "embedding.api_calls", tags={"model": self._model, "input_type": input_type}
        )
        return vectors, token_counts

    # ── Retry with exponential backoff ─────────────────────

    async def _retry_with_backoff(
        self,
        func: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Call a function with retry and exponential backoff + jitter.

        Retries on TRANSIENT failures only:
        - EmbeddingServiceUnavailable (network, 5xx, auth errors)
        - EmbeddingTimeout (request timed out)
        - EmbeddingError with code "rate_limited" (HTTP 429)

        Does NOT retry on:
        - EmbeddingError (validation/format errors — code != rate_limited)
        - Any non-EmbeddingError exception
        """
        last_exception: Exception | None = None

        for attempt in range(1, self._max_retries + 2):  # +1 for initial attempt
            try:
                return await func(*args, **kwargs)
            except EmbeddingTimeout as e:
                last_exception = e
                if attempt > self._max_retries:
                    get_metrics().increment("embedding.retry_exhausted", tags={"reason": "timeout"})
                    raise
                wait = self._backoff ** (attempt - 1)
                jitter = random.uniform(0, wait * 0.2)  # 0-20% random jitter
                total_wait = min(wait + jitter, 30.0)
                logger.warning(
                    "Embedding timeout — retrying",
                    attempt=attempt,
                    max_retries=self._max_retries,
                    wait_seconds=round(total_wait, 2),
                    error=str(e),
                )
                get_metrics().increment(
                    "embedding.retry", tags={"reason": "timeout", "attempt": str(attempt)}
                )
                await asyncio.sleep(total_wait)

            except EmbeddingServiceUnavailable as e:
                last_exception = e
                if attempt > self._max_retries:
                    get_metrics().increment(
                        "embedding.retry_exhausted", tags={"reason": "service_unavailable"}
                    )
                    raise
                wait = self._backoff ** (attempt - 1)
                jitter = random.uniform(0, wait * 0.2)
                total_wait = min(wait + jitter, 30.0)
                logger.warning(
                    "Embedding service unavailable — retrying",
                    attempt=attempt,
                    max_retries=self._max_retries,
                    wait_seconds=round(total_wait, 2),
                    error=str(e),
                )
                get_metrics().increment(
                    "embedding.retry", tags={"reason": "unavailable", "attempt": str(attempt)}
                )
                await asyncio.sleep(total_wait)

            except EmbeddingError as e:
                if e.code == "rate_limited":
                    # Rate limited — retry with backoff
                    last_exception = e
                    if attempt > self._max_retries:
                        get_metrics().increment(
                            "embedding.retry_exhausted", tags={"reason": "rate_limited"}
                        )
                        raise
                    wait = self._backoff ** (attempt - 1) * 2  # Double wait for rate limits
                    jitter = random.uniform(0, wait * 0.2)
                    total_wait = min(wait + jitter, 60.0)  # Higher cap for rate limits
                    logger.warning(
                        "Rate limited — retrying",
                        attempt=attempt,
                        max_retries=self._max_retries,
                        wait_seconds=round(total_wait, 2),
                    )
                    get_metrics().increment(
                        "embedding.retry", tags={"reason": "rate_limited", "attempt": str(attempt)}
                    )
                    await asyncio.sleep(total_wait)
                else:
                    # Non-retryable embedding error (validation, format, etc.)
                    raise

        raise last_exception or EmbeddingError("Retry policy exhausted")

    # ── Validation — 15 checks ────────────────────────────

    def _validate_inputs(
        self,
        texts: list[str],
        metadata: list[dict[str, Any]] | None,
    ) -> None:
        """Validate input texts before embedding.

        Raises EmbeddingError immediately for invalid inputs — no API calls
        are made for clearly invalid requests.
        """
        if not texts:
            raise EmbeddingError("Empty document list — nothing to embed", code="empty_input")

        # Metadata length check
        if metadata is not None and len(metadata) != len(texts):
            raise EmbeddingError(
                f"Metadata length ({len(metadata)}) does not match texts length ({len(texts)})",
                code="metadata_mismatch",
            )

        for i, text in enumerate(texts):
            if not isinstance(text, str):
                raise EmbeddingError(
                    f"Text at index {i} is not a string: {type(text).__name__}",
                    code="invalid_text_type",
                )
            if not text.strip():
                raise EmbeddingError(
                    f"Text at index {i} is empty or whitespace-only",
                    code="empty_text",
                )
            if len(text) > self._max_tokens * 4:  # Rough chars-to-tokens estimate
                raise EmbeddingError(
                    f"Text at index {i} exceeds max input tokens "
                    f"(~{len(text)} chars > max {self._max_tokens * 4} chars)",
                    code="text_too_long",
                )

        # Check for duplicate input texts
        seen: set[str] = set()
        for i, text in enumerate(texts):
            if text in seen:
                logger.warning("Duplicate input text detected", index=i, text_preview=text[:80])
            seen.add(text)

        # Check for duplicate IDs in metadata
        # Note: `chunk_id` is checked before `document_id` so that multiple chunks
        # from the same document are NOT flagged as duplicates.
        if metadata:
            seen_ids: set[str] = set()
            duplicate_ids: list[str] = []
            for i, meta in enumerate(metadata):
                doc_id = meta.get("id") or meta.get("chunk_id") or meta.get("document_id")
                if doc_id:
                    if doc_id in seen_ids:
                        duplicate_ids.append(doc_id)
                    seen_ids.add(doc_id)
            if duplicate_ids:
                raise DuplicateInputIdError(sorted(set(duplicate_ids)))

        # Language validation
        self._validate_languages(texts)

    def _validate_batch_response(
        self,
        batch_texts: list[str],
        vectors: list[list[float]],
        token_counts: list[int],
        batch_start_idx: int,
    ) -> None:
        """Validate the response from a batch embedding call."""
        if not vectors:
            raise EmbeddingError(
                f"Empty vectors in batch response (batch starts at {batch_start_idx})",
                code="empty_batch_response",
            )

        # Mismatched input/output counts
        if len(vectors) != len(batch_texts):
            raise EmbeddingError(
                f"Batch response count mismatch: sent {len(batch_texts)} texts, "
                f"received {len(vectors)} vectors",
                code="batch_count_mismatch",
            )

        if token_counts and len(token_counts) != len(vectors):
            raise EmbeddingError(
                f"Token count mismatch: {len(token_counts)} counts for {len(vectors)} vectors",
                code="token_count_mismatch",
            )

        # Consistent dimensions across batch
        if vectors:
            dim = len(vectors[0])
            for i, vec in enumerate(vectors):
                if len(vec) != dim:
                    raise EmbeddingError(
                        f"Inconsistent dimensions in batch: vector 0 has {dim}, "
                        f"vector {i} has {len(vec)}",
                        code="inconsistent_dimensions",
                    )

    def _validate_vector(self, vector: list[float]) -> None:
        """Validate a single embedding vector.

        Checks: non-empty, dimension match, NaN, Inf.
        """
        if not vector:
            raise EmbeddingError("Empty embedding vector", code="empty_vector")

        if self._dimension and len(vector) != self._dimension:
            raise EmbeddingError(
                f"Embedding dimension mismatch: expected {self._dimension}, got {len(vector)}",
                code="dimension_mismatch",
            )

        for i, val in enumerate(vector):
            if val != val:
                raise EmbeddingError(
                    f"NaN value at index {i} in embedding vector",
                    code="nan_embedding",
                )
            if math.isinf(val):
                raise EmbeddingError(
                    f"Inf value at index {i} in embedding vector",
                    code="inf_embedding",
                )

    def _validate_languages(self, texts: list[str]) -> None:
        """Validate that texts don't use unsupported languages.

        This is a best-effort check using language detection on a sample
        of texts. Falls back to supported languages from the provider.

        Raises:
            UnsupportedLanguageError: If unsupported languages are detected.
        """
        if not self._language_validation_enabled:
            return

        supported = self._supported_langs
        if len(supported) == 1:
            # Attempt language detection on non-trivial text samples
            detected: set[str] = set()
            for text in texts:
                if len(text) < 20:
                    continue
                try:
                    lang = _detect_lang(text)
                    if lang not in supported:
                        detected.add(lang)
                except Exception:
                    pass
            if detected:
                raise UnsupportedLanguageError(
                    unsupported_languages=sorted(detected),
                    supported=supported,
                )

    def _validate_no_duplicates(self, vectors: list[list[float]]) -> None:
        """Check for duplicate (identical) embeddings within a batch.

        Logs a warning for exact duplicates. Does NOT raise because slightly
        different inputs can legitimately produce very similar vectors.
        """
        if len(vectors) < 2:
            return

        seen: set[tuple[float, ...]] = set()
        for i, vec in enumerate(vectors):
            rounded = tuple(round(v, 6) for v in vec)  # 6 decimal places tolerance
            if rounded in seen:
                logger.warning(
                    "Duplicate embedding vector detected",
                    index=i,
                    vector_preview=f"{vec[:3]}... (dim={len(vec)})",
                )
                get_metrics().increment("embedding.duplicate_vector", tags={"model": self._model})
            seen.add(rounded)
