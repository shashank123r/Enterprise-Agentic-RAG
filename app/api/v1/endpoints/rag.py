"""RAG API endpoints — chat, streaming, and validation.

All endpoints use the RAGOrchestrator singleton for consistent configuration.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.dependencies import get_db
from app.rag.exceptions import RAGGroundingError, RAGLLMError, RAGLLMUnavailable
from app.rag.orchestrator import RAGOrchestrator
from app.rag.schemas import RAGRequest, RAGResponse, ValidateRequest, ValidateResponse
from app.rag.response_validator import ResponseValidator
from app.retrieval.services.retrieval_service import RetrievalService
from app.api.v1.endpoints.retrieval import get_retrieval_service

router = APIRouter(prefix="/chat", tags=["rag"])

# ── Singleton ─────────────────────────────────
_rag_orchestrator: RAGOrchestrator | None = None


async def get_rag_orchestrator(
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
) -> RAGOrchestrator:
    """Get the application-scoped RAGOrchestrator singleton."""
    global _rag_orchestrator
    if _rag_orchestrator is None:
        _rag_orchestrator = RAGOrchestrator(retrieval_service=retrieval_service)
    return _rag_orchestrator


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
    request.stream = True

    async def event_stream():
        """Generate SSE events for the streaming response."""
        try:
            # We run the full pipeline but capture the streamed output
            # The orchestrator handles streaming internally
            # For SSE, we stream token-by-token and send metadata at the end
            from app.rag.schemas import RAGResponse as RAGResp
            from app.rag.token_budget import TokenBudget
            from app.rag.context_manager import RAGContextManager

            retrieval_service = orchestrator._retrieval
            context_manager = RAGContextManager()

            # Step 1: Indicating retrieval
            yield f"data: {json.dumps({'type': 'status', 'message': 'Retrieving context...'})}\n\n"

            # Step 2: Retrieve using the search parameters
            retrieval_result = await retrieval_service.search(
                query=request.question,
                collection_name=request.collection_name,
                method=request.retrieval_method,
                top_k=request.top_k,
                filters=request.filters or {},
                rerank=request.rerank,
                query_rewrite=request.query_rewrite,
                max_context_tokens=request.max_context_tokens,
            )

            chunks = retrieval_result.chunks

            # Step 3: Build context
            budget = TokenBudget(
                model=orchestrator._llm_model,
                max_context_tokens=request.max_context_tokens,
                max_response_tokens=request.max_response_tokens,
            )
            context = await context_manager.build_context(chunks, budget)

            # Step 4: Build prompt
            messages = await orchestrator._prompt_builder.build(
                context=context,
                question=request.question,
                budget=budget,
                history=request.conversation_history,
            )

            yield f"data: {json.dumps({'type': 'status', 'message': 'Generating answer...'})}\n\n"

            # Step 5: Stream LLM response
            full_text = ""
            llm_payload = {
                "model": orchestrator._llm_model,
                "messages": messages,
                "temperature": request.temperature or 0.1,
                "max_tokens": request.max_response_tokens or 1024,
                "stream": True,
            }

            async with orchestrator.client.stream(
                "POST", orchestrator._llm_api_url, json=llm_payload
            ) as response:
                if response.status_code != 200:
                    yield f"data: {json.dumps({'type': 'error', 'message': f'LLM error: HTTP {response.status_code}'})}\n\n"
                    yield "data: [DONE]\n\n"
                    return

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
                            yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"
                    except json.JSONDecodeError:
                        continue

            # Step 6: Grounding validation
            import time
            start = time.monotonic()
            grounding = await orchestrator._grounding_validator.validate(
                answer=full_text,
                chunks=chunks,
                question=request.question,
            )

            # Step 7: Citations
            citation_indices = orchestrator._grounding_validator._extract_citations(full_text)
            citations = orchestrator._citation_merger.build_citations(chunks, citation_indices)

            # Step 8: Send final metadata
            metadata = {
                "type": "metadata",
                "citations": [c.model_dump() for c in citations],
                "grounding_valid": grounding["valid"],
                "grounding_issues": grounding["issues"],
                "citation_count": len(citations),
                "chunks_count": len(chunks),
            }
            yield f"data: {json.dumps(metadata)}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
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
        RetrievedChunk(
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
        response = await orchestrator.client.get(orchestrator._llm_api_url.replace("/chat/completions", "/health"))
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
