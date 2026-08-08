"""RAG API endpoints — chat, streaming, and validation.

All endpoints use the RAGOrchestrator singleton for consistent configuration.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.v1.endpoints.retrieval import get_retrieval_service
from app.rag.exceptions import RAGGroundingError, RAGLLMError, RAGLLMUnavailable
from app.rag.orchestrator import RAGOrchestrator
from app.rag.response_validator import ResponseValidator
from app.rag.schemas import RAGRequest, RAGResponse, ValidateRequest, ValidateResponse
from app.retrieval.services.retrieval_service import RetrievalService

router = APIRouter(prefix="/chat", tags=["rag"])


async def get_rag_orchestrator(
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
) -> RAGOrchestrator:
    """Get a RAGOrchestrator for this request.

    The orchestrator is lightweight (no persistent connections of its own);
    all heavy resources are in the injected retrieval_service singleton.
    """
    return RAGOrchestrator(retrieval_service=retrieval_service)


# ── Chat endpoint ─────────────────────────────


@router.post("", summary="Answer a question using RAG")
async def chat(
    request: RAGRequest,
    orchestrator: RAGOrchestrator = Depends(get_rag_orchestrator),
) -> RAGResponse:
    """Answer a question using the full RAG pipeline.

    Retrieves relevant context from the knowledge base, constructs a prompt,
    calls the LLM, validates grounding, and returns a structured response
    with citations.

    Supports streaming via the /chat/stream endpoint.
    """
    try:
        return await orchestrator.answer(
            question=request.question,
            collection_name=request.collection_name,
            top_k=request.top_k,
            retrieval_method=request.retrieval_method,
            rerank=request.rerank,
            query_rewrite=request.query_rewrite,
            filters=request.filters,
            max_context_tokens=request.max_context_tokens,
            max_response_tokens=request.max_response_tokens,
            temperature=request.temperature,
            stream=False,
            conversation_history=request.conversation_history,
        )
    except RAGLLMUnavailable as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except RAGLLMError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    except RAGGroundingError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ── Streaming endpoint ────────────────────────


@router.post("/stream", summary="Stream a RAG answer")
async def chat_stream(
    request: RAGRequest,
    orchestrator: RAGOrchestrator = Depends(get_rag_orchestrator),
):
    """Answer a question using RAG with streaming response.

    Retrieves context, builds prompt, and streams the LLM response
    as Server-Sent Events (SSE). Final metadata includes citations
    and grounding info.
    """

    async def event_stream():
        async for event in orchestrator.answer_stream(
            question=request.question,
            collection_name=request.collection_name,
            top_k=request.top_k,
            retrieval_method=request.retrieval_method,
            rerank=request.rerank,
            query_rewrite=request.query_rewrite,
            filters=request.filters,
            max_context_tokens=request.max_context_tokens,
            max_response_tokens=request.max_response_tokens,
            temperature=request.temperature,
            conversation_history=request.conversation_history,
        ):
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Validation endpoint ───────────────────────


@router.post("/validate", summary="Validate a generated answer")
async def validate_answer(
    request: ValidateRequest,
) -> ValidateResponse:
    """Validate a generated answer for grounding and quality.

    Checks that the answer is properly supported by the provided source chunks
    and has valid citations.
    """
    validator = ResponseValidator()

    # Structural validation
    validation = await validator.validate(request.answer)

    # Grounding validation
    from app.rag.grounding import GroundingValidator

    grounding_validator = GroundingValidator()

    # Convert RAGChunk list to RetrievedChunk-like structure
    # for the grounding validator
    from app.retrieval.schemas import RetrievedChunk

    chunks = [
        RetrievedChunk(  # type: ignore[call-arg]
            chunk_id=c.chunk_id,
            document_id=c.document_id,
            text=c.text_preview,
            score=c.score,
            page_number=c.page_number,
            section_title=c.section_title,
            metadata={"document_title": c.document_title},
        )
        for c in request.chunks
    ]

    grounding = await grounding_validator.validate(
        answer=request.answer,
        chunks=chunks,
        question=request.question,
    )

    issues: list[str] = []
    issues.extend(validation.get("issues", []))
    issues.extend(grounding.get("issues", []))

    return ValidateResponse(
        grounding_valid=grounding["valid"],
        issues=issues,
        unsupported_statements=grounding.get("unsupported_statements", []),
        suggested_fixes=[],
    )


# ── Health endpoint ───────────────────────────


@router.get("/health", summary="RAG system health check")
async def health(
    orchestrator: RAGOrchestrator = Depends(get_rag_orchestrator),
) -> dict[str, Any]:
    """Check the RAG system health.

    Returns:
        Dict with LLM endpoint status and retrieval service status.
    """
    # Check LLM endpoint
    llm_ok = False
    try:
        response = await orchestrator.client.get(
            orchestrator._llm_api_url.replace("/chat/completions", "/health")
        )
        llm_ok = response.status_code == 200
    except Exception:
        llm_ok = False

    # Check retrieval service
    retrieval_health = await orchestrator._retrieval.health_check()

    return {
        "llm_endpoint": {
            "url": orchestrator._llm_api_url,
            "model": orchestrator._llm_model,
            "healthy": llm_ok,
        },
        "retrieval": retrieval_health,
        "rag_ready": llm_ok and retrieval_health.get("retrieval_ready", False),
    }
