"""Unit tests for the RAGOrchestrator.

All external dependencies (LLM, retrieval service) are mocked so these tests
run without any network access or infrastructure.
"""

from __future__ import annotations

import json
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.rag.orchestrator import RAGOrchestrator
from app.rag.schemas import RAGResponse
from app.retrieval.schemas import RetrievedChunk, RetrievalResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_chunk(chunk_id: str = "c1", text: str = "The answer is 42. [1]") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id="doc1",
        text=text,
        score=0.9,
        metadata={"document_title": "Test Doc", "source": "test.pdf"},
    )


def _make_retrieval_result(chunks: list[RetrievedChunk] | None = None) -> RetrievalResult:
    return RetrievalResult(
        query="What is the answer?",
        chunks=chunks or [_make_chunk()],
        total_results=1,
    )


def _mock_llm_response(content: str = "The answer is 42. [1]") -> AsyncMock:
    """Build a mock httpx response that returns a non-streaming JSON body."""
    body = {
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
    }
    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value=body)
    return mock_response


@pytest.fixture
def mock_retrieval_service() -> AsyncMock:
    svc = AsyncMock()
    svc.search = AsyncMock(return_value=_make_retrieval_result())
    svc.health_check = AsyncMock(return_value={"retrieval_ready": True})
    return svc


@pytest.fixture
def orchestrator(mock_retrieval_service: AsyncMock) -> RAGOrchestrator:
    return RAGOrchestrator(
        retrieval_service=mock_retrieval_service,
        llm_api_url="http://fake-llm/v1/chat/completions",
        llm_api_key="fake-key",
        llm_model="test-model",
    )


# ---------------------------------------------------------------------------
# answer() tests
# ---------------------------------------------------------------------------


class TestOrchestratorAnswer:
    @pytest.mark.asyncio
    async def test_returns_rag_response(self, orchestrator: RAGOrchestrator):
        """answer() returns a RAGResponse with an answer string."""
        mock_resp = _mock_llm_response("The answer is 42. [1]")

        with patch.object(orchestrator, "client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_resp)
            result = await orchestrator.answer(question="What is the answer?")

        assert isinstance(result, RAGResponse)
        assert result.answer
        assert result.llm_model == "test-model"

    @pytest.mark.asyncio
    async def test_retrieval_service_called_with_question(
        self,
        orchestrator: RAGOrchestrator,
        mock_retrieval_service: AsyncMock,
    ):
        """answer() forwards the question to the retrieval service."""
        mock_resp = _mock_llm_response()

        with patch.object(orchestrator, "client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_resp)
            await orchestrator.answer(question="What is the meaning of life?")

        mock_retrieval_service.search.assert_awaited_once()
        call_kwargs = mock_retrieval_service.search.call_args.kwargs
        assert call_kwargs.get("query") == "What is the meaning of life?"

    @pytest.mark.asyncio
    async def test_duration_metrics_populated(self, orchestrator: RAGOrchestrator):
        """Timing metrics are always present and positive."""
        mock_resp = _mock_llm_response()

        with patch.object(orchestrator, "client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_resp)
            result = await orchestrator.answer(question="Q?")

        assert result.total_duration_ms >= 0
        assert result.retrieval_duration_ms >= 0
        assert result.llm_duration_ms >= 0

    @pytest.mark.asyncio
    async def test_no_chunks_returns_answer_without_citations(
        self,
        orchestrator: RAGOrchestrator,
        mock_retrieval_service: AsyncMock,
    ):
        """When retrieval returns no chunks, answer is returned with empty citations."""
        mock_retrieval_service.search = AsyncMock(
            return_value=_make_retrieval_result(chunks=[])
        )
        mock_resp = _mock_llm_response("I don't know.")

        with patch.object(orchestrator, "client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_resp)
            result = await orchestrator.answer(question="Unknown?")

        assert isinstance(result, RAGResponse)
        assert result.citations == []


# ---------------------------------------------------------------------------
# answer_stream() tests
# ---------------------------------------------------------------------------


async def _collect_stream(gen) -> list[dict]:
    """Collect all events from an async generator into a list."""
    events = []
    async for event in gen:
        events.append(event)
    return events


class TestOrchestratorAnswerStream:
    @pytest.mark.asyncio
    async def test_stream_yields_status_then_tokens_then_metadata(
        self,
        orchestrator: RAGOrchestrator,
    ):
        """answer_stream() must yield: status, token(s), metadata — in that order."""
        # Build a fake SSE stream from the LLM
        sse_lines = [
            'data: {"choices": [{"delta": {"content": "Hello"}}]}',
            'data: {"choices": [{"delta": {"content": " world"}}]}',
            "data: [DONE]",
        ]

        async def fake_aiter_lines():
            for line in sse_lines:
                yield line

        mock_stream_response = AsyncMock()
        mock_stream_response.__aenter__ = AsyncMock(return_value=mock_stream_response)
        mock_stream_response.__aexit__ = AsyncMock(return_value=None)
        mock_stream_response.status_code = 200
        mock_stream_response.aiter_lines = fake_aiter_lines
        mock_stream_response.aread = AsyncMock(return_value=b"")

        with patch.object(orchestrator, "client") as mock_client:
            mock_client.stream = MagicMock(return_value=mock_stream_response)

            events = await _collect_stream(
                orchestrator.answer_stream(question="What is hello world?")
            )

        types = [e["type"] for e in events]
        assert "status" in types
        assert "token" in types
        assert "metadata" in types

        # metadata always last
        assert types[-1] == "metadata"

        # tokens appear before metadata
        token_idx = max(i for i, t in enumerate(types) if t == "token")
        meta_idx = types.index("metadata")
        assert token_idx < meta_idx

    @pytest.mark.asyncio
    async def test_stream_emits_correct_token_content(
        self,
        orchestrator: RAGOrchestrator,
    ):
        """Token events concatenate to the full LLM response."""
        tokens = ["The ", "answer ", "is ", "42."]
        sse_lines = [
            f'data: {{"choices": [{{"delta": {{"content": {json.dumps(t)}}}}}]}}'
            for t in tokens
        ] + ["data: [DONE]"]

        async def fake_aiter_lines():
            for line in sse_lines:
                yield line

        mock_stream_response = AsyncMock()
        mock_stream_response.__aenter__ = AsyncMock(return_value=mock_stream_response)
        mock_stream_response.__aexit__ = AsyncMock(return_value=None)
        mock_stream_response.status_code = 200
        mock_stream_response.aiter_lines = fake_aiter_lines
        mock_stream_response.aread = AsyncMock(return_value=b"")

        with patch.object(orchestrator, "client") as mock_client:
            mock_client.stream = MagicMock(return_value=mock_stream_response)
            events = await _collect_stream(
                orchestrator.answer_stream(question="Q?")
            )

        token_events = [e for e in events if e["type"] == "token"]
        full_text = "".join(e["content"] for e in token_events)
        assert full_text == "The answer is 42."

    @pytest.mark.asyncio
    async def test_stream_yields_error_event_on_llm_failure(
        self,
        orchestrator: RAGOrchestrator,
    ):
        """When the LLM returns non-200, an error event is yielded."""
        mock_stream_response = AsyncMock()
        mock_stream_response.__aenter__ = AsyncMock(return_value=mock_stream_response)
        mock_stream_response.__aexit__ = AsyncMock(return_value=None)
        mock_stream_response.status_code = 503
        mock_stream_response.aread = AsyncMock(return_value=b"Service Unavailable")

        with patch.object(orchestrator, "client") as mock_client:
            mock_client.stream = MagicMock(return_value=mock_stream_response)
            events = await _collect_stream(
                orchestrator.answer_stream(question="Q?")
            )

        error_events = [e for e in events if e["type"] == "error"]
        assert error_events, "Expected at least one error event on LLM failure"
        assert "503" in error_events[0]["message"]

    @pytest.mark.asyncio
    async def test_stream_error_on_retrieval_failure(
        self,
        orchestrator: RAGOrchestrator,
        mock_retrieval_service: AsyncMock,
    ):
        """When retrieval raises, the stream yields a single error event."""
        mock_retrieval_service.search = AsyncMock(
            side_effect=RuntimeError("Milvus unavailable")
        )

        events = await _collect_stream(
            orchestrator.answer_stream(question="Q?")
        )

        assert any(e["type"] == "error" for e in events)
        assert not any(e["type"] == "token" for e in events)
