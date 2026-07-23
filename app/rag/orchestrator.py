"""RAG Orchestrator — coordinates the full RAG pipeline.

Question
  ↓
Query normalization (via RetrievalService)
  ↓
Retrieval Engine (via RetrievalService)
  ↓
Context Builder
  ↓
Token budget management
  ↓
Prompt construction
  ↓
LLM request (NVIDIA NIM)
  ↓
Grounding validation
  ↓
Citation merge
  ↓
Structured response
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.rag.citation_merger import CitationMerger
from app.rag.context_manager import RAGContextManager
from app.rag.exceptions import RAGLLMError, RAGLLMUnavailable
from app.rag.grounding import GroundingValidator
from app.rag.metrics import record_rag_metrics
from app.rag.prompt_builder import PromptBuilder
from app.rag.response_validator import ResponseValidator
from app.rag.schemas import CitationInfo, RAGChunk, RAGResponse
from app.rag.token_budget import TokenBudget
from app.retrieval.schemas import RetrievedChunk
from app.retrieval.services.retrieval_service import RetrievalService

logger = get_logger(__name__)


class RAGOrchestrator:
    """Orchestrates the end-to-end RAG pipeline.

    Composes retrieval, prompt construction, LLM interaction,
    grounding validation, and citation merging.

    Usage:
        orchestrator = RAGOrchestrator(retrieval_service)
        response = await orchestrator.answer(question="What is X?")
    """

    def __init__(
        self,
        retrieval_service: RetrievalService,
        llm_api_url: str | None = None,
        llm_api_key: str | None = None,
        llm_model: str | None = None,
        llm_timeout: int = 60,
    ) -> None:
        self._retrieval = retrieval_service
        self._llm_api_url = (llm_api_url or str(settings.NIM_CHAT_URL)).rstrip("/")
        self._llm_api_key = llm_api_key or settings.NIM_API_KEY
        self._llm_model = llm_model or settings.NIM_MODEL_CHAT
        self._llm_timeout = llm_timeout

        self._context_manager = RAGContextManager()
        self._prompt_builder = PromptBuilder()
        self._grounding_validator = GroundingValidator()
        self._citation_merger = CitationMerger()
        self._response_validator = ResponseValidator()

        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Lazy-initialized HTTP client for LLM calls."""
        if self._client is None:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            if self._llm_api_key:
                headers["Authorization"] = f"Bearer {self._llm_api_key}"

            self._client = httpx.AsyncClient(
                headers=headers,
                timeout=httpx.Timeout(self._llm_timeout),
            )
        return self._client

    async def answer(
        self,
        question: str,
        collection_name: str = "documents",
        top_k: int = 10,
        retrieval_method: str = "hybrid",
        rerank: bool = True,
        query_rewrite: bool = True,
        filters: dict[str, Any] | None = None,
        max_context_tokens: int | None = 4096,
        max_response_tokens: int | None = 1024,
        temperature: float | None = 0.1,
        stream: bool = False,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> RAGResponse:
        """Execute the full RAG pipeline and return a grounded answer.

        Args:
            question: User's question.
            collection_name: Milvus collection to search.
            top_k: Number of chunks to retrieve.
            retrieval_method: Retrieval method to use.
            rerank: Whether to apply reranking.
            query_rewrite: Whether to apply query rewriting.
            filters: Metadata filters for retrieval.
            max_context_tokens: Max tokens for context window.
            max_response_tokens: Max tokens for the response.
            temperature: LLM temperature.
            stream: Whether to stream the response.
            conversation_history: Optional previous messages.

        Returns:
            RAGResponse with answer, citations, and metrics.

        Raises:
            RAGLLMUnavailable: If LLM endpoint is unreachable.
            RAGLLMError: If LLM returns an error.
        """
        start_time = time.monotonic()

        # ── Step 1: Retrieval ──────────────────
        retrieval_duration = 0.0
        chunks: list[RetrievedChunk] = []
        retrieval_result = None

        with self._timing() as rt:
            retrieval_result = await self._retrieval.search(
                query=question,
                collection_name=collection_name,
                method=retrieval_method,
                top_k=top_k,
                filters=filters or {},
                rerank=rerank,
                query_rewrite=query_rewrite,
                max_context_tokens=max_context_tokens,
            )
            retrieval_duration = rt.duration
            chunks = retrieval_result.chunks

        # ── Step 2: Token budget ───────────────
        budget = TokenBudget(
            model=self._llm_model,
            max_context_tokens=max_context_tokens,
            max_response_tokens=max_response_tokens,
        )

        # ── Step 3: Build context ──────────────
        context = await self._context_manager.build_context(chunks, budget)

        # ── Step 4: Build prompt ───────────────
        messages = await self._prompt_builder.build(
            context=context,
            question=question,
            budget=budget,
            history=conversation_history,
        )

        # ── Step 5: LLM call ───────────────────
        llm_duration = 0.0
        prompt_tokens = 0
        completion_tokens = 0
        llm_model_used = self._llm_model

        llm_temp = temperature or 0.1
        llm_max_tokens = max_response_tokens or 1024

        if stream:
            llm_start = time.monotonic()
            answer_text, token_info = await self._call_llm_stream(
                messages, temperature=llm_temp, max_tokens=llm_max_tokens,
            )
            llm_duration = time.monotonic() - llm_start
            prompt_tokens = token_info.get("prompt_tokens", 0)
            completion_tokens = token_info.get("completion_tokens", 0)
            llm_model_used = token_info.get("model", self._llm_model)
        else:
            llm_start = time.monotonic()
            answer_text, token_info = await self._call_llm(
                messages, temperature=llm_temp, max_tokens=llm_max_tokens,
            )
            llm_duration = time.monotonic() - llm_start
            prompt_tokens = token_info.get("prompt_tokens", 0)
            completion_tokens = token_info.get("completion_tokens", 0)
            llm_model_used = token_info.get("model", self._llm_model)

        # ── Step 6: Validate response ──────────
        validation = await self._response_validator.validate(answer_text)
        if not validation["valid"]:
            logger.warning(
                "Response validation failed",
                issues=validation["issues"],
            )

        # ── Step 7: Grounding check ────────────
        grounding = await self._grounding_validator.validate(
            answer=answer_text,
            chunks=chunks,
            question=question,
        )

        # ── Step 8: Build citations ────────────
        citation_indices = self._grounding_validator._extract_citations(answer_text)
        citations = self._citation_merger.build_citations(chunks, citation_indices)

        # ── Step 9: Build RAGChunks -------------
        rag_chunks = self._build_rag_chunks(chunks)

        # ── Step 10: Final response ────────────
        total_duration = (time.monotonic() - start_time) * 1000

        record_rag_metrics(
            llm_model=llm_model_used,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_duration_ms=round(total_duration, 2),
            llm_duration_ms=round(llm_duration * 1000, 2),
            retrieval_duration_ms=round(retrieval_duration * 1000, 2),
            citation_count=len(citations),
            grounding_valid=grounding["valid"],
            streamed=stream,
        )

        logger.info(
            "RAG pipeline complete",
            question_preview=question[:60],
            total_duration_ms=round(total_duration, 1),
            chunks_retrieved=len(chunks),
            citations=len(citations),
            grounding_ok=grounding["valid"],
            llm_tokens=prompt_tokens + completion_tokens,
        )

        return RAGResponse(
            answer=answer_text,
            citations=citations,
            chunks=rag_chunks,
            grounding_valid=grounding["valid"],
            grounding_issues=grounding["issues"],
            llm_model=llm_model_used,
            total_duration_ms=round(total_duration, 2),
            retrieval_duration_ms=round(retrieval_duration * 1000, 2),
            llm_duration_ms=round(llm_duration * 1000, 2),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )

    # ── LLM calls ──────────────────────────────

    async def _call_llm(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> tuple[str, dict[str, Any]]:
        """Call the LLM API (non-streaming).

        Args:
            messages: List of message dicts.
            temperature: LLM temperature (0.0-2.0).
            max_tokens: Maximum response tokens.

        Returns:
            Tuple of (response_text, token_info_dict).

        Raises:
            RAGLLMUnavailable: If LLM endpoint is unreachable.
            RAGLLMError: If LLM returns an error.
        """
        payload = {
            "model": self._llm_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

        try:
            response = await self.client.post(
                self._llm_api_url,
                json=payload,
            )

            if response.status_code != 200:
                raise RAGLLMError(
                    f"LLM returned HTTP {response.status_code}: {response.text[:200]}"
                )

            data = response.json()
            choice = data.get("choices", [{}])[0]
            answer_text = choice.get("message", {}).get("content", "")

            usage = data.get("usage", {})
            token_info = {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
                "model": data.get("model", self._llm_model),
            }

            return answer_text, token_info

        except httpx.TimeoutException:
            raise RAGLLMUnavailable("LLM request timed out")
        except httpx.ConnectError as e:
            raise RAGLLMUnavailable(f"Cannot connect to LLM endpoint: {e}")
        except httpx.HTTPError as e:
            raise RAGLLMUnavailable(f"LLM HTTP error: {e}")

    async def _call_llm_stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> tuple[str, dict[str, Any]]:
        """Call the LLM API with streaming.

        Args:
            messages: List of message dicts.
            temperature: LLM temperature (0.0-2.0).
            max_tokens: Maximum response tokens.

        Returns:
            Tuple of (full_response_text, token_info_dict).
        """
        payload = {
            "model": self._llm_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        full_text = ""
        token_info: dict[str, Any] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "model": self._llm_model,
        }

        try:
            async with self.client.stream("POST", self._llm_api_url, json=payload) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    raise RAGLLMError(
                        f"LLM returned HTTP {response.status_code}: {error_text[:200]}"
                    )

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue

                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break

                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            full_text += content

                        usage = chunk.get("usage", {})
                        if usage:
                            token_info["prompt_tokens"] = usage.get("prompt_tokens", 0)
                            token_info["completion_tokens"] = usage.get("completion_tokens", 0)
                            if chunk.get("model"):
                                token_info["model"] = chunk["model"]
                    except json.JSONDecodeError:
                        continue

            return full_text, token_info

        except httpx.TimeoutException:
            raise RAGLLMUnavailable("LLM streaming request timed out")
        except httpx.ConnectError as e:
            raise RAGLLMUnavailable(f"Cannot connect to LLM endpoint: {e}")
        except httpx.HTTPError as e:
            raise RAGLLMUnavailable(f"LLM HTTP error: {e}")

    # ── Helpers ────────────────────────────────

    @staticmethod
    def _build_rag_chunks(chunks: list[RetrievedChunk]) -> list[RAGChunk]:
        """Convert RetrievedChunk objects to RAGChunk for the response."""
        rag_chunks = []
        for c in chunks:
            doc_title = (
                c.metadata.get("document_title")
                or c.metadata.get("title")
                or ""
            )
            rag_chunks.append(
                RAGChunk(
                    chunk_id=c.chunk_id,
                    document_id=c.document_id,
                    document_title=doc_title,
                    text_preview=c.text[:300],
                    page_number=c.page_number,
                    section_title=c.section_title,
                    score=c.score,
                    retrieval_method=c.retrieval_source,
                )
            )
        return rag_chunks

    @staticmethod
    def _timing() -> _Timer:
        """Create a context manager for timing operations."""
        return _Timer()


class _Timer:
    """Simple context manager for timing operations."""

    def __init__(self) -> None:
        self.duration: float = 0.0

    def __enter__(self) -> "_Timer":
        self._start = time.monotonic()
        return self

    def __exit__(self, *args: Any) -> None:
        self.duration = time.monotonic() - self._start
