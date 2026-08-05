"""Document management API endpoints — all storage through StorageProvider.

No direct pathlib, shutil, hashlib, or magic operations. Every filesystem
call delegates to the injected StorageProvider.
"""

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_413_CONTENT_TOO_LARGE, HTTP_413_REQUEST_ENTITY_TOO_LARGE

from app.core.config import settings
from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, ALLOWED_DOCUMENT_TYPES
from app.core.dependencies import get_current_user_id, get_db, get_storage, require_role
from app.core.constants import Role
from app.core.exceptions import NotFoundError, ConflictError, ValidationError
from app.core.logging import get_logger
from app.ingestion.executor import run_in_executor
from app.ingestion.pipeline import IngestionPipeline, compute_checksum, validate_file
from app.ingestion.repository import (
    DocumentChunkRepository,
    DocumentImageRepository,
    DocumentRepository,
    DocumentTableRepository,
    DocumentVersionRepository,
    IngestionJobRepository,
)
from app.ingestion.schemas import (
    ChunkResponse,
    DocumentListResponse,
    DocumentReplaceResponse,
    DocumentResponse,
    DocumentStatsResponse,
    DocumentUploadResponse,
    DocumentVersionResponse,
    ExtractTextResponse,
    ImageResponse,
    IngestionStatusResponse,
    TableResponse,
)
from app.storage import StorageProvider

logger = get_logger(__name__)

router = APIRouter()

# Shared ARQ pool — created once per process, reused across requests
_arq_pool = None


async def _get_arq_pool():
    """Return the process-level ARQ pool, creating it on first call."""
    global _arq_pool
    if _arq_pool is None:
        try:
            from arq import create_pool

            _arq_pool = await create_pool(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD or None,
            )
        except Exception as e:
            logger.warning("Failed to create ARQ pool", error=str(e))
            return None
    return _arq_pool


@router.post(
    "/upload",
    summary="Upload document",
    description="Upload a document for ingestion into the knowledge base.",
    response_model=DocumentUploadResponse,
    status_code=201,
)
async def upload_document(
    file: UploadFile = File(..., description="Document file to upload"),
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
    storage: StorageProvider = Depends(get_storage),
) -> dict[str, Any]:
    """Upload a document file for ingestion."""
    max_size = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    content = await file.read()
    if len(content) > max_size:
        raise HTTPException(
            status_code=HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File size exceeds maximum of {settings.MAX_UPLOAD_SIZE_MB}MB",
        )

    # Detect MIME type via StorageProvider
    import magic

    def _detect_mime() -> str:
        detected = magic.from_buffer(content[:2048], mime=True)
        if detected == "application/octet-stream":
            return file.content_type or "application/octet-stream"
        return detected

    mime_type = await run_in_executor(_detect_mime)

    if mime_type not in ALLOWED_DOCUMENT_TYPES:
        raise ValidationError(
            message=f"Unsupported file type: {mime_type}",
            code="unsupported_file_type",
        )

    # Save file to temp storage and compute checksum
    temp_filename = f"{uuid4()}_{file.filename}"
    import hashlib

    checksum = hashlib.sha256(content).hexdigest()
    temp_path = await storage.generate_temp_path(temp_filename)
    await storage.save(temp_path, content)

    # Check for duplicates
    doc_repo = DocumentRepository(db)
    existing = await doc_repo.get_by_checksum(checksum)
    if existing and not existing.is_deleted:
        await storage.delete(temp_path)
        raise ConflictError(
            message="A document with identical content already exists",
            code="duplicate_document",
            details={"existing_document_id": existing.id},
        )

    # Validate file
    errors = await validate_file(temp_path, mime_type, storage)
    if errors:
        await storage.delete(temp_path)
        raise ValidationError(
            message="File validation failed",
            code="validation_error",
            details={"errors": errors},
        )

    # Create document record
    document = await doc_repo.create(
        filename=temp_filename,
        original_filename=file.filename or "untitled",
        mime_type=mime_type,
        size_bytes=len(content),
        checksum=checksum,
        status="pending",
        user_id=user_id,
    )

    # Create ingestion job
    job_repo = IngestionJobRepository(db)
    job = await job_repo.create(
        document_id=document.id,
        status="queued",
        progress=0.0,
        current_stage="queued",
    )

    # Move file to permanent storage
    permanent_path = await storage.generate_storage_path("documents", document.id)
    await storage.move(temp_path, permanent_path)

    # Enqueue background job via shared ARQ pool
    try:
        arq_pool = await _get_arq_pool()
        if arq_pool:
            await arq_pool.enqueue_job(
                "process_document",
                document_id=document.id,
                file_path=permanent_path,
                mime_type=mime_type,
                user_id=user_id,
            )
    except Exception as e:
        logger.warning("Failed to enqueue ingestion job", error=str(e))

    return {
        "document": DocumentResponse.model_validate(document),
        "job": IngestionStatusResponse.model_validate(job),
    }


@router.get(
    "/",
    summary="List documents",
    response_model=DocumentListResponse,
)
async def list_documents(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    status: str | None = Query(default=None, description="Filter by status"),
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> DocumentListResponse:
    """List documents with pagination."""
    doc_repo = DocumentRepository(db)
    documents, total = await doc_repo.list_documents(
        page=page, size=size, status=status, user_id=user_id
    )
    items = [DocumentResponse.model_validate(d) for d in documents]
    pages = max(1, (total + size - 1) // size)
    return DocumentListResponse(items=items, total=total, page=page, size=size, pages=pages)


@router.get(
    "/{document_id}",
    summary="Get document metadata",
    response_model=DocumentResponse,
)
async def get_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
) -> DocumentResponse:
    """Get document metadata by ID."""
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(document_id)
    if doc is None or doc.is_deleted:
        raise NotFoundError(message="Document not found", code="document_not_found")
    return DocumentResponse.model_validate(doc)


@router.get(
    "/{document_id}/status",
    summary="Get ingestion status",
    response_model=IngestionStatusResponse,
)
async def get_ingestion_status(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
) -> IngestionStatusResponse:
    """Get the current ingestion job status."""
    job_repo = IngestionJobRepository(db)
    job = await job_repo.get_job_by_document(document_id)
    if job is None:
        raise NotFoundError(
            message="No ingestion job found for this document",
            code="job_not_found",
        )
    return IngestionStatusResponse.model_validate(job)


@router.get(
    "/{document_id}/text",
    summary="Download extracted text",
    response_model=ExtractTextResponse,
)
async def get_extracted_text(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
) -> ExtractTextResponse:
    """Download the full extracted text from all chunks."""
    chunk_repo = DocumentChunkRepository(db)
    chunks = await chunk_repo.get_chunks_by_document(document_id)

    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(document_id)
    if doc is None:
        raise NotFoundError(message="Document not found", code="document_not_found")

    full_text = "\n\n".join(c.content for c in chunks)
    total_chars = sum(c.char_count for c in chunks)

    return ExtractTextResponse(
        document_id=document_id,
        filename=doc.original_filename,
        total_chunks=len(chunks),
        total_characters=total_chars,
        text=full_text,
    )


@router.get(
    "/{document_id}/chunks",
    summary="Get document chunks",
    response_model=list[ChunkResponse],
)
async def get_chunks(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
) -> list[ChunkResponse]:
    """Get all chunks for a document."""
    chunk_repo = DocumentChunkRepository(db)
    chunks = await chunk_repo.get_chunks_by_document(document_id)
    return [ChunkResponse.model_validate(c) for c in chunks]


@router.get(
    "/{document_id}/tables",
    summary="Get document tables",
    response_model=list[TableResponse],
)
async def get_tables(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
) -> list[TableResponse]:
    """Get all extracted tables."""
    table_repo = DocumentTableRepository(db)
    tables = await table_repo.get_tables_by_document(document_id)
    return [TableResponse.model_validate(t) for t in tables]


@router.get(
    "/{document_id}/images",
    summary="Get document images",
    response_model=list[ImageResponse],
)
async def get_images(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
) -> list[ImageResponse]:
    """Get all extracted images."""
    image_repo = DocumentImageRepository(db)
    images = await image_repo.get_images_by_document(document_id)
    return [ImageResponse.model_validate(i) for i in images]


@router.get(
    "/{document_id}/versions",
    summary="Get document versions",
    response_model=list[DocumentVersionResponse],
)
async def get_versions(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
) -> list[DocumentVersionResponse]:
    """Get version history."""
    version_repo = DocumentVersionRepository(db)
    versions = await version_repo.get_versions(document_id)
    return [DocumentVersionResponse.model_validate(v) for v in versions]


@router.get(
    "/{document_id}/stats",
    summary="Get document stats",
    response_model=DocumentStatsResponse,
)
async def get_stats(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
) -> DocumentStatsResponse:
    """Get document processing statistics."""
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(document_id)
    if doc is None or doc.is_deleted:
        raise NotFoundError(message="Document not found", code="document_not_found")
    return DocumentStatsResponse.model_validate(doc)


@router.post(
    "/{document_id}/replace",
    summary="Replace document",
    description="Replace an existing document with a new version.",
    response_model=DocumentReplaceResponse,
)
async def replace_document(
    document_id: str,
    file: UploadFile = File(..., description="New document file"),
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
    storage: StorageProvider = Depends(get_storage),
) -> DocumentReplaceResponse:
    """Replace an existing document (creates new version)."""
    doc_repo = DocumentRepository(db)
    existing = await doc_repo.get_by_id(document_id)
    if existing is None or existing.is_deleted:
        raise NotFoundError(message="Document not found", code="document_not_found")

    content = await file.read()
    max_size = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(content) > max_size:
        raise HTTPException(status_code=HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large")

    # Detect MIME type and compute checksum via StorageProvider
    import magic
    import hashlib

    def _detect_and_hash() -> tuple[str, str]:
        mime = magic.from_buffer(content[:2048], mime=True)
        if mime == "application/octet-stream":
            mime = file.content_type or mime
        cksum = hashlib.sha256(content).hexdigest()
        return mime, cksum

    mime_type, checksum = await run_in_executor(_detect_and_hash)

    if mime_type not in ALLOWED_DOCUMENT_TYPES:
        raise ValidationError(
            message=f"Unsupported file type: {mime_type}", code="unsupported_file_type"
        )

    # Create new version record
    version_repo = DocumentVersionRepository(db)
    version_number = await version_repo.get_next_version_number(document_id)
    await version_repo.create(
        document_id=document_id,
        version_number=version_number,
        filename=file.filename or "untitled",
        size_bytes=len(content),
        checksum=checksum,
        changes=f"Replaced by user {user_id}",
    )

    # Save new file via StorageProvider
    file_path = await storage.generate_storage_path("documents", document_id)
    await storage.save(file_path, content)

    # Update document record
    doc = await doc_repo.update(
        document_id,
        filename=f"{document_id}",
        original_filename=file.filename or existing.original_filename,
        mime_type=mime_type,
        size_bytes=len(content),
        checksum=checksum,
        status="pending",
        current_version=version_number,
    )

    # Create new ingestion job
    job_repo = IngestionJobRepository(db)
    job = await job_repo.create(
        document_id=document_id,
        status="queued",
        progress=0.0,
        current_stage="queued",
    )

    return DocumentReplaceResponse(
        document=DocumentResponse.model_validate(doc),
        job=IngestionStatusResponse.model_validate(job),
        new_version=version_number,
    )


@router.post(
    "/{document_id}/retry",
    summary="Retry ingestion",
    description="Retry failed document ingestion.",
    response_model=IngestionStatusResponse,
)
async def retry_ingestion(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
    storage: StorageProvider = Depends(get_storage),
) -> IngestionStatusResponse:
    """Retry a failed ingestion."""
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(document_id)
    if doc is None or doc.is_deleted:
        raise NotFoundError(message="Document not found", code="document_not_found")

    # Reset document status
    await doc_repo.update_status(document_id, "pending")

    # Create new job
    job_repo = IngestionJobRepository(db)
    job = await job_repo.create(
        document_id=document_id,
        status="queued",
        progress=0.0,
        current_stage="queued",
    )

    # Enqueue via shared ARQ pool
    file_path = await storage.generate_storage_path("documents", document_id)
    try:
        arq_pool = await _get_arq_pool()
        if arq_pool:
            await arq_pool.enqueue_job(
                "process_document",
                document_id=document_id,
                file_path=file_path,
                mime_type=doc.mime_type,
                user_id=_user_id,
            )
    except Exception as e:
        logger.warning("Failed to enqueue retry job", error=str(e))

    return IngestionStatusResponse.model_validate(job)


@router.post(
    "/{document_id}/cancel",
    summary="Cancel ingestion",
    response_model=IngestionStatusResponse,
)
async def cancel_ingestion(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
) -> IngestionStatusResponse:
    """Cancel an ingestion job."""
    job_repo = IngestionJobRepository(db)
    job = await job_repo.get_job_by_document(document_id)
    if job is None:
        raise NotFoundError(message="No active job found", code="job_not_found")

    if job.status not in ("queued", "processing"):
        raise ValidationError(
            message=f"Cannot cancel job in status '{job.status}'",
            code="invalid_job_status",
        )

    job = await job_repo.mark_cancelled(job.id)
    return IngestionStatusResponse.model_validate(job)


@router.delete(
    "/{document_id}",
    summary="Delete document",
    description="Soft delete a document from the knowledge base.",
    response_model=dict[str, str],
)
async def delete_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
) -> dict[str, str]:
    """Soft delete a document."""
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(document_id)
    if doc is None or doc.is_deleted:
        raise NotFoundError(message="Document not found", code="document_not_found")

    await doc_repo.soft_delete(document_id)
    return {"message": "Document deleted successfully", "code": "document_deleted"}
