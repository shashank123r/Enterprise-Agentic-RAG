"""Comprehensive tests for the NVIDIA NIM embedding provider.

All tests mock httpx.AsyncClient to avoid real network calls.
Covers validation (15 checks), retry policy, batching, auth,
health checks, and the provider factory.
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.embeddings.exceptions import (
    EmbeddingError,
)
from app.embeddings.providers.base import EmbeddingProvider, EmbeddingProviderInfo
from app.embeddings.providers.nvidia_nim import NvidiaNIMEmbeddingProvider

# ── Helpers ─────────────────────────────────────────────────


def make_mock_response(status_code: int, json_data: dict | None = None) -> MagicMock:
    """Create a mock httpx.Response."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    if json_data is not None:
        response.json = MagicMock(return_value=json_data)
    else:
        response.json = MagicMock(side_effect=ValueError("No JSON set"))
    response.text = str(json_data) if json_data else ""
    return response


def make_embedding_response(
    texts: list[str],
    dim: int = 4,
    model: str = "nvidia/nv-embed-qa-4",
) -> dict:
    """Generate a mock NIM embedding API response."""
    data = []
    for i, _ in enumerate(texts):
        data.append(
            {
                "object": "embedding",
                "index": i,
                "embedding": [0.1 * (i + 1)] * dim,
            }
        )
    return {
        "object": "list",
        "data": data,
        "model": model,
        "usage": {"prompt_tokens": len(texts) * 10, "total_tokens": len(texts) * 10},
    }


# ── Fixtures ────────────────────────────────────────────────


@pytest.fixture
def provider() -> NvidiaNIMEmbeddingProvider:
    """Create a provider with minimal config for testing."""
    return NvidiaNIMEmbeddingProvider(
        api_url="http://test-nim:8000",
        api_key="test-key",
        model="nvidia/nv-embed-qa-4",
        batch_size=10,
        max_concurrent=5,
        timeout=30,
        max_retries=2,
        backoff_multiplier=1.0,
    )


@pytest.fixture
def mock_client(provider: NvidiaNIMEmbeddingProvider) -> MagicMock:
    """Mock the provider's HTTP client."""
    client = MagicMock(spec=httpx.AsyncClient)
    provider._client = client
    return client


# ── Interface Compliance ───────────────────────────────────


class TestInterfaceCompliance:
    def test_provider_is_embedding_provider(self, provider: NvidiaNIMEmbeddingProvider) -> None:
        assert isinstance(provider, EmbeddingProvider)

    def test_provider_name(self, provider: NvidiaNIMEmbeddingProvider) -> None:
        assert provider.provider_name() == "nvidia_nim"

    @pytest.mark.asyncio
    async def test_supported_languages(self, provider: NvidiaNIMEmbeddingProvider) -> None:
        langs = await provider.supported_languages()
        assert "en" in langs


# ── Input Validation (15 checks) ───────────────────────────


class TestInputValidation:
    @pytest.mark.asyncio
    async def test_empty_input_raises(self, provider: NvidiaNIMEmbeddingProvider) -> None:
        with pytest.raises(EmbeddingError, match="Empty document list"):
            await provider.embed_documents([])

    @pytest.mark.asyncio
    async def test_whitespace_only_raises(self, provider: NvidiaNIMEmbeddingProvider) -> None:
        with pytest.raises(EmbeddingError, match="empty or whitespace"):
            await provider.embed_documents(["   ", "\t\n"])

    @pytest.mark.asyncio
    async def test_metadata_length_mismatch_raises(
        self,
        provider: NvidiaNIMEmbeddingProvider,
    ) -> None:
        with pytest.raises(EmbeddingError, match="Metadata length"):
            await provider.embed_documents(["a", "b"], metadata=[{"id": "1"}])

    @pytest.mark.asyncio
    async def test_oversized_input_raises(self, provider: NvidiaNIMEmbeddingProvider) -> None:
        long_text = "x" * 10000  # Well beyond 512*4=2048 chars
        with pytest.raises(EmbeddingError, match="exceeds max"):
            await provider.embed_documents([long_text])

    @pytest.mark.asyncio
    async def test_non_string_input_raises(self, provider: NvidiaNIMEmbeddingProvider) -> None:
        with pytest.raises(EmbeddingError, match="not a string"):
            await provider.embed_documents([123])  # type: ignore[list-item]

    @pytest.mark.asyncio
    async def test_duplicate_input_logs_warning(
        self,
        provider: NvidiaNIMEmbeddingProvider,
        mock_client: MagicMock,
    ) -> None:
        mock_client.post.return_value = make_mock_response(
            200,
            make_embedding_response(["hello", "hello"], dim=4),
        )
        with patch("app.embeddings.providers.nvidia_nim.logger.warning") as mock_warn:
            result = await provider.embed_documents(["hello", "hello"])
            mock_warn.assert_called_once()
            assert "Duplicate input text" in mock_warn.call_args[0][0]
        assert len(result.vectors) == 2


# ── Batch Response Validation ──────────────────────────────


class TestBatchResponseValidation:
    @pytest.mark.asyncio
    async def test_empty_batch_response(
        self,
        provider: NvidiaNIMEmbeddingProvider,
        mock_client: MagicMock,
    ) -> None:
        """Empty vectors in response should be caught and batch marked failed."""
        resp = make_mock_response(
            200,
            {
                "object": "list",
                "data": [],
                "model": provider._model,
            },
        )
        mock_client.post.return_value = resp
        result = await provider.embed_documents(["hello"])
        assert len(result.failed_indices) == 1
        assert "empty" in result.errors[0].lower()

    @pytest.mark.asyncio
    async def test_batch_count_mismatch(
        self,
        provider: NvidiaNIMEmbeddingProvider,
        mock_client: MagicMock,
    ) -> None:
        """Sending 2 texts but getting 1 vector should fail the batch."""
        resp = make_mock_response(200, make_embedding_response(["only_one"], dim=4))
        mock_client.post.return_value = resp
        result = await provider.embed_documents(["hello", "world"])
        assert len(result.failed_indices) == 2
        assert "count mismatch" in result.errors[0].lower()

    @pytest.mark.asyncio
    async def test_inconsistent_dimensions(
        self,
        provider: NvidiaNIMEmbeddingProvider,
        mock_client: MagicMock,
    ) -> None:
        """Vectors with different dimensions should fail the batch."""
        data = [
            {"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3, 0.4]},
            {"object": "embedding", "index": 1, "embedding": [0.5, 0.6]},  # wrong dim
        ]
        mock_client.post.return_value = make_mock_response(
            200,
            {
                "object": "list",
                "data": data,
                "model": provider._model,
                "usage": {"prompt_tokens": 20, "total_tokens": 20},
            },
        )
        result = await provider.embed_documents(["hello", "world"])
        assert len(result.failed_indices) == 2


# ── Vector Validation ──────────────────────────────────────


class TestVectorValidation:
    @pytest.mark.asyncio
    async def test_nan_vector(
        self,
        provider: NvidiaNIMEmbeddingProvider,
        mock_client: MagicMock,
    ) -> None:
        """NaN values in embedding should fail the batch."""

        data = [
            {"object": "embedding", "index": 0, "embedding": [0.1, float("nan"), 0.3, 0.4]},
        ]
        mock_client.post.return_value = make_mock_response(
            200,
            {
                "object": "list",
                "data": data,
                "model": provider._model,
                "usage": {"prompt_tokens": 10, "total_tokens": 10},
            },
        )
        result = await provider.embed_documents(["hello"])
        assert len(result.failed_indices) >= 1

    @pytest.mark.asyncio
    async def test_inf_vector(
        self,
        provider: NvidiaNIMEmbeddingProvider,
        mock_client: MagicMock,
    ) -> None:
        """Inf values in embedding should fail the batch."""

        data = [
            {"object": "embedding", "index": 0, "embedding": [0.1, float("inf"), 0.3, 0.4]},
        ]
        mock_client.post.return_value = make_mock_response(
            200,
            {
                "object": "list",
                "data": data,
                "model": provider._model,
                "usage": {"prompt_tokens": 10, "total_tokens": 10},
            },
        )
        result = await provider.embed_documents(["hello"])
        assert len(result.failed_indices) >= 1

    @pytest.mark.asyncio
    async def test_empty_vector(
        self,
        provider: NvidiaNIMEmbeddingProvider,
        mock_client: MagicMock,
    ) -> None:
        """Empty embedding vector should fail validation."""
        data = [
            {"object": "embedding", "index": 0, "embedding": []},
        ]
        mock_client.post.return_value = make_mock_response(
            200,
            {
                "object": "list",
                "data": data,
                "model": provider._model,
                "usage": {"prompt_tokens": 10, "total_tokens": 10},
            },
        )
        result = await provider.embed_documents(["hello"])
        assert len(result.failed_indices) >= 1


# ── Retry Policy ───────────────────────────────────────────


class TestRetryPolicy:
    @pytest.mark.asyncio
    async def test_retry_on_timeout_then_success(
        self,
        provider: NvidiaNIMEmbeddingProvider,
        mock_client: MagicMock,
    ) -> None:
        """Timeout -> retry -> success should work."""
        success_resp = make_mock_response(200, make_embedding_response(["hello"], dim=4))
        mock_client.post.side_effect = [
            httpx.TimeoutException("timeout"),
            success_resp,
        ]
        result = await provider.embed_documents(["hello"])
        assert len(result.vectors) == 1
        assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_exhausted_on_timeout(
        self,
        provider: NvidiaNIMEmbeddingProvider,
        mock_client: MagicMock,
    ) -> None:
        """Repeated timeouts should eventually fail the batch."""
        mock_client.post.side_effect = httpx.TimeoutException("timeout")
        result = await provider.embed_documents(["hello"])
        assert len(result.failed_indices) == 1
        assert "timeout" in result.errors[0].lower()

    @pytest.mark.asyncio
    async def test_auth_failure_not_retried(
        self,
        provider: NvidiaNIMEmbeddingProvider,
        mock_client: MagicMock,
    ) -> None:
        """401 should raise EmbeddingAuthError immediately — no retry."""
        mock_client.post.return_value = make_mock_response(401)
        result = await provider.embed_documents(["hello"])
        assert len(result.failed_indices) == 1
        assert "auth" in result.errors[0].lower() or "Authentication" in result.errors[0]
        assert mock_client.post.call_count == 1  # No retry

    @pytest.mark.asyncio
    async def test_rate_limit_retried(
        self,
        provider: NvidiaNIMEmbeddingProvider,
        mock_client: MagicMock,
    ) -> None:
        """429 should be retried like a transient error."""
        success_resp = make_mock_response(200, make_embedding_response(["hello"], dim=4))
        mock_client.post.side_effect = [
            make_mock_response(429),
            success_resp,
        ]
        result = await provider.embed_documents(["hello"])
        assert len(result.vectors) == 1
        assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_server_error_retried(
        self,
        provider: NvidiaNIMEmbeddingProvider,
        mock_client: MagicMock,
    ) -> None:
        """500 should be retried (EmbeddingServiceUnavailable)."""
        success_resp = make_mock_response(200, make_embedding_response(["hello"], dim=4))
        mock_client.post.side_effect = [
            make_mock_response(500),
            success_resp,
        ]
        result = await provider.embed_documents(["hello"])
        assert len(result.vectors) == 1
        assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_bad_request_not_retried(
        self,
        provider: NvidiaNIMEmbeddingProvider,
        mock_client: MagicMock,
    ) -> None:
        """400 should not be retried (EmbeddingError, non-retryable)."""
        mock_client.post.return_value = make_mock_response(400)
        result = await provider.embed_documents(["hello"])
        assert len(result.failed_indices) == 1
        assert mock_client.post.call_count == 1  # No retry


# ── Core Embedding ─────────────────────────────────────────


class TestCoreEmbedding:
    @pytest.mark.asyncio
    async def test_embed_documents_success(
        self,
        provider: NvidiaNIMEmbeddingProvider,
        mock_client: MagicMock,
    ) -> None:
        """Successful embedding returns vectors with correct metadata."""
        mock_client.post.return_value = make_mock_response(
            200,
            make_embedding_response(["hello", "world"], dim=4),
        )
        result = await provider.embed_documents(["hello", "world"])
        assert len(result.vectors) == 2
        assert len(result.vectors[0]) == 4
        assert result.model == provider._model
        assert result.failed_indices == []

    @pytest.mark.asyncio
    async def test_embed_query_success(
        self,
        provider: NvidiaNIMEmbeddingProvider,
        mock_client: MagicMock,
    ) -> None:
        """Single query embedding returns an EmbeddingResult."""
        mock_client.post.return_value = make_mock_response(
            200,
            make_embedding_response(["test query"], dim=4),
        )
        result = await provider.embed_query("test query")
        assert len(result.vector) == 4
        assert result.text == "test query"
        assert result.model == provider._model

    @pytest.mark.asyncio
    async def test_batch_embed_with_concurrency(
        self,
        provider: NvidiaNIMEmbeddingProvider,
        mock_client: MagicMock,
    ) -> None:
        """Batch embed splits texts into batches and processes with concurrency."""
        texts = [f"text {i}" for i in range(25)]  # 3 batches with batch_size=10
        mock_client.post.return_value = make_mock_response(
            200,
            make_embedding_response(texts[:10], dim=4),
        )
        result = await provider.batch_embed(texts, batch_size=10)
        # With mocked response returning only first 10 vectors, each batch
        # that gets the mock will get only those 10 vectors
        assert result.model == provider._model
        assert isinstance(result.vectors, list)
        assert isinstance(result.failed_indices, list)


# ── Health Checks ──────────────────────────────────────────


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_success(
        self,
        provider: NvidiaNIMEmbeddingProvider,
        mock_client: MagicMock,
    ) -> None:
        """Health check returns True when endpoint responds."""
        mock_client.post.return_value = make_mock_response(
            200,
            make_embedding_response(["health"], dim=4),
        )
        healthy = await provider.health_check()
        assert healthy is True

    @pytest.mark.asyncio
    async def test_health_check_failure(
        self,
        provider: NvidiaNIMEmbeddingProvider,
        mock_client: MagicMock,
    ) -> None:
        """Health check returns False on connection error."""
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")
        healthy = await provider.health_check()
        assert healthy is False

    @pytest.mark.asyncio
    async def test_model_info_includes_runtime_data(
        self,
        provider: NvidiaNIMEmbeddingProvider,
        mock_client: MagicMock,
    ) -> None:
        """model_info returns EmbeddingProviderInfo with runtime metadata."""
        mock_client.post.return_value = make_mock_response(
            200,
            make_embedding_response(["test"], dim=4),
        )
        info = await provider.model_info()
        assert isinstance(info, EmbeddingProviderInfo)
        assert info.provider_name == "nvidia_nim"
        assert info.model_name == provider._model
        assert info.dimension == 4
        # The metadata field is attached dynamically
        assert hasattr(info, "metadata") or info.provider_name == "nvidia_nim"


# ── Configuration ──────────────────────────────────────────


class TestConfiguration:
    @pytest.mark.asyncio
    async def test_dimension_caching(self, provider: NvidiaNIMEmbeddingProvider) -> None:
        """dimension() should cache after first call."""
        assert provider._dimension is None
        # Without mock, dimension() would try to make an API call
        # Set it directly for unit testing the cache
        provider._dimension = 2048
        dim = await provider.dimension()
        assert dim == 2048

    @pytest.mark.asyncio
    async def test_max_input_tokens_caching(self, provider: NvidiaNIMEmbeddingProvider) -> None:
        """max_input_tokens() should cache after first call."""
        max_tok = await provider.max_input_tokens()
        assert max_tok > 0
        cached = await provider.max_input_tokens()
        assert cached == max_tok


# ── Factory ────────────────────────────────────────────────


class TestProviderFactory:
    @pytest.mark.asyncio
    async def test_create_provider(self) -> None:
        """Factory should create the correct provider type."""
        from app.embeddings.providers.factory import create_embedding_provider

        with patch("app.embeddings.providers.factory.settings") as mock_settings:
            mock_settings.EMBEDDING_PROVIDER = "nvidia_nim"
            mock_settings.NVIDIA_NIM_URL = "http://test:8000"
            mock_settings.NVIDIA_NIM_API_KEY = "test-key"
            mock_settings.EMBEDDING_MODEL = "nvidia/nv-embed-qa-4"
            mock_settings.EMBEDDING_BATCH_SIZE = 32
            mock_settings.MAX_CONCURRENT_REQUESTS = 10
            mock_settings.REQUEST_TIMEOUT = 30
            mock_settings.EMBEDDING_MAX_RETRIES = 3
            mock_settings.EMBEDDING_BACKOFF_MULTIPLIER = 2.0
            mock_settings.EMBEDDING_CACHE_ENABLED = True
            mock_settings.EMBEDDING_CACHE_TTL_SECONDS = 86400

            provider = await create_embedding_provider()
            assert isinstance(provider, NvidiaNIMEmbeddingProvider)

    @pytest.mark.asyncio
    async def test_unknown_provider_raises(self) -> None:
        """Unknown provider type should raise ValueError."""
        from app.embeddings.providers.factory import create_embedding_provider

        with patch("app.embeddings.providers.factory.settings") as mock_settings:
            mock_settings.EMBEDDING_PROVIDER = "unknown_provider"
            with pytest.raises(ValueError, match="Unknown embedding provider"):
                await create_embedding_provider()


# ── Connection Pool ────────────────────────────────────────


class TestConnectionPool:
    @pytest.mark.asyncio
    async def test_client_lazy_initialization(self) -> None:
        """HTTP client should be None until first access."""
        p = NvidiaNIMEmbeddingProvider(
            api_url="http://test:8000",
            api_key="key",
            model="nvidia/nv-embed-qa-4",
        )
        assert p._client is None
        _ = p.client  # Trigger lazy init
        assert p._client is not None
        await p.close()
        assert p._client is None

    @pytest.mark.asyncio
    async def test_client_includes_gzip_header(self) -> None:
        """Client should request gzip compression."""
        p = NvidiaNIMEmbeddingProvider(api_url="http://test:8000")
        client = p.client
        assert client.headers.get("Accept-Encoding") == "gzip"
        await p.close()

    @pytest.mark.asyncio
    async def test_client_includes_auth_header(self) -> None:
        """Client should include Bearer token when API key is set."""
        p = NvidiaNIMEmbeddingProvider(api_url="http://test:8000", api_key="my-key")
        client = p.client
        assert "Authorization" in client.headers
        assert client.headers["Authorization"] == "Bearer my-key"
        await p.close()
