"""Indexing API endpoints — manage the full indexing lifecycle.

All endpoints are async with dependency injection through FastAPI.
The IndexingService is application-scoped (singleton), so job tracking
and cancellation work correctly across requests.

Authentication and RBAC are enforced via middleware dependencies.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db as get_db_session
from app.embeddings.services.indexing_service import (
    IndexingService,
    get_indexing_service_instance,
)
from app.ingestion.repository import DocumentChunkRepository
from app.repositories.indexing_job_repository import IndexingJobRepository

router = APIRouter(prefix="/indexing", tags=["indexing"])


def _get_service() -> IndexingService:
    """Get the application-scoped IndexingService singleton.

    This is NOT created per-request — the singleton is initialized
    during FastAPI lifespan startup. This ensures ``_active_jobs``
    and task tracking are shared across all requests (fixes C2).
    """
    return get_indexing_service_instance()


@router.post("/start", summary="Start indexing a document")
async def start_indexing(
    document_id: str,
    collection_name: str = "documents",
    use_arq: bool = False,
    embedding_model: str | None = None,
    vector_dimension: int | None = None,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Start a new indexing job for a document.

    Retrieves the document's chunks from the ingestion repository,
    then runs the indexing pipeline (in-process via TaskManager or
    via ARQ for durable background processing).

    Returns the created job metadata.
    """
    service = _get_service()

    # Load chunks from ingestion repository (fixes C3 — no more TODO)
    chunk_repo = DocumentChunkRepository(db)
    chunks = await chunk_repo.get_chunks_by_document(document_id)

    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No chunks found for document {document_id}. " "Ingest the document first.",
        )

    # Convert ORM chunks to dict format expected by IndexingService
    chunk_dicts = []
    for c in chunks:
        meta = dict(c.custom_metadata) if c.custom_metadata else {}
        meta["document_id"] = document_id
        meta["chunk_id"] = c.id
        chunk_dicts.append(
            {
                "chunk_id": c.id,
                "text": c.content,
                "metadata": meta,
                "checksum": c.content_checksum,
                "chunk_index": c.chunk_index,
                "page_number": c.page_number,
                "section_title": c.section_title,
                "language": c.language or "unknown",
                "version": 1,
                "source": "",
            }
        )

    job = await service.start_indexing(
        db=db,
        document_id=document_id,
        chunks=chunk_dicts,
        collection_name=collection_name,
        use_arq=use_arq,
        embedding_model=embedding_model,
        vector_dimension=vector_dimension,
    )
    return {
        "job_id": job.id,
        "document_id": job.document_id,
        "status": job.status,
        "collection_name": job.collection_name,
        "total_chunks": job.total_chunks,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }


@router.post("/{job_id}/cancel", summary="Cancel an indexing job")
async def cancel_indexing(
    job_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Cancel an active indexing job.

    Jobs in 'completed' or 'cancelled' status cannot be cancelled.
    """
    service = _get_service()
    repo = IndexingJobRepository(db)
    try:
        job = await service.cancel_indexing(job_id, repo)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    return {
        "job_id": job.id,
        "status": job.status,
        "message": "Cancellation requested for indexing job",
    }


@router.post("/{job_id}/retry", summary="Retry a failed indexing job")
async def retry_indexing(
    job_id: str,
    collection_name: str = "documents",
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Retry a failed indexing job.

    Loads the document's chunks and re-queues the job.
    """
    service = _get_service()

    # Load chunks for retry
    chunk_repo = DocumentChunkRepository(db)
    repo = IndexingJobRepository(db)
    job = await repo.get_by_id(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    chunks = await chunk_repo.get_chunks_by_document(job.document_id)
    chunk_dicts = _chunks_to_dicts(chunks, job.document_id)

    try:
        retried = await service.retry_indexing(
            job_id=job_id,
            db=db,
            chunks=chunk_dicts,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    return {
        "job_id": retried.id,
        "status": retried.status,
        "document_id": retried.document_id,
        "retry_count": retried.retry_count,
        "message": "Job queued for retry",
    }


# ── Literal GET routes (must be before /{job_id} to avoid path param capture) ──


@router.get("/", summary="List indexing jobs")
async def list_jobs(
    document_id: str | None = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db_session),
) -> list[dict[str, Any]]:
    """List indexing jobs, optionally filtered by document ID.

    Returns up to ``limit`` jobs, ordered by creation date (newest first).
    """
    repo = IndexingJobRepository(db)
    jobs = await IndexingService.list_jobs(repo, document_id=document_id, limit=limit)

    return [
        {
            "job_id": j.id,
            "document_id": j.document_id,
            "collection_name": j.collection_name,
            "status": j.status,
            "progress_percent": j.progress_percent,
            "total_chunks": j.total_chunks,
            "processed_chunks": j.processed_chunks,
            "retry_count": j.retry_count,
            "error_message": j.error_message,
            "created_at": j.created_at.isoformat() if j.created_at else None,
        }
        for j in jobs
    ]


@router.get("/stats/summary", summary="Get indexing statistics")
async def indexing_stats(
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Get aggregate indexing statistics."""
    repo = IndexingJobRepository(db)
    counts = await IndexingService.get_job_counts_by_status(repo)
    active = await IndexingService.get_active_jobs_list(repo)

    return {
        "counts_by_status": counts,
        "active_jobs_count": len(active),
        "active_jobs": [
            {
                "job_id": j.id,
                "document_id": j.document_id,
                "status": j.status,
                "progress_percent": j.progress_percent,
            }
            for j in active
        ],
    }


@router.get("/health/embedding", summary="Check embedding provider health")
async def health_embedding() -> dict[str, Any]:
    """Check if the embedding provider is reachable and responding.

    Returns:
        Dict with 'healthy' status, provider name, model, and latency.
    """
    service = _get_service()
    return await service.health_check_embedding()


@router.get("/health/vector-store", summary="Check vector store health")
async def health_vector_store() -> dict[str, Any]:
    """Check if the vector store (Milvus) is reachable and responding.

    Returns:
        Dict with 'healthy' status and collection count.
    """
    service = _get_service()
    return await service.health_check_vector_store()


@router.get("/health", summary="Check indexing system health")
async def health_indexing() -> dict[str, Any]:
    """Get aggregate indexing health status.

    Returns:
        Dict with active task count and system status.
    """
    service = _get_service()
    return await service.health_check_indexing()


@router.delete("/documents/{document_id}", summary="Delete document index")
async def delete_document_index(
    document_id: str,
    collection_name: str = "documents",
) -> dict[str, Any]:
    """Delete all indexed vectors for a document from the vector store."""
    service = _get_service()
    deleted = await service.delete_document_index(document_id, collection_name)

    return {
        "document_id": document_id,
        "collection_name": collection_name,
        "vectors_deleted": deleted,
        "message": "Document index deleted",
    }


@router.post("/rebuild", summary="Rebuild document index")
async def rebuild_document_index(
    document_id: str,
    collection_name: str = "documents",
    use_arq: bool = False,
    embedding_model: str | None = None,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Delete and re-index a document.

    Loads chunks from the ingestion repository, then deletes existing
    vectors and creates a new indexing job.

    Returns the new job metadata.
    """
    service = _get_service()

    # Load chunks from ingestion repository (fixes C3)
    chunk_repo = DocumentChunkRepository(db)
    chunks = await chunk_repo.get_chunks_by_document(document_id)

    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No chunks found for document {document_id}. " "Ingest the document first.",
        )

    chunk_dicts = _chunks_to_dicts(chunks, document_id)

    job = await service.rebuild_document_index(
        db=db,
        document_id=document_id,
        chunks=chunk_dicts,
        collection_name=collection_name,
        use_arq=use_arq,
        embedding_model=embedding_model,
    )

    return {
        "job_id": job.id,
        "document_id": job.document_id,
        "status": job.status,
        "message": "Document index rebuild started",
    }


# ── Parameterized GET route (must come AFTER all literal paths) ──


@router.get("/{job_id}", summary="Get indexing job status")
async def get_job_status(
    job_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Get the current status and progress of an indexing job."""
    repo = IndexingJobRepository(db)
    job = await IndexingService.get_job_status(job_id, repo)

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    return {
        "job_id": job.id,
        "document_id": job.document_id,
        "collection_name": job.collection_name,
        "status": job.status,
        "progress_percent": job.progress_percent,
        "total_chunks": job.total_chunks,
        "processed_chunks": job.processed_chunks,
        "failed_chunks": job.failed_chunks,
        "retry_count": job.retry_count,
        "cache_hits": job.cache_hits,
        "error_message": job.error_message,
        "embedding_model": job.embedding_model,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


# ── Helpers ─────────────────────────────────


def _chunks_to_dicts(chunks: list[Any], document_id: str) -> list[dict[str, Any]]:
    """Convert DocumentChunk ORM objects to dict format for IndexingService.

    Args:
        chunks: List of DocumentChunk ORM instances.
        document_id: Parent document UUID.

    Returns:
        List of chunk dicts with text, metadata, checksum, etc.
    """
    chunk_dicts = []
    for c in chunks:
        meta = dict(c.custom_metadata) if c.custom_metadata else {}
        meta["document_id"] = document_id
        meta["chunk_id"] = c.id
        chunk_dicts.append(
            {
                "chunk_id": c.id,
                "text": c.content,
                "metadata": meta,
                "checksum": c.content_checksum,
                "chunk_index": c.chunk_index,
                "page_number": c.page_number,
                "section_title": c.section_title,
                "language": c.language or "unknown",
                "version": 1,
                "source": "",
            }
        )
    return chunk_dicts
