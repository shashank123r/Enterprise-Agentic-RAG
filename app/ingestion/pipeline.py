"""Main ingestion pipeline — all file I/O through StorageProvider.

The pipeline has zero knowledge of the filesystem. All persistence
operations delegate to the injected StorageProvider.
"""

import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.ingestion.cleaners import create_default_pipeline
from app.ingestion.chunking import chunking_pipeline
from app.ingestion.detectors import language_detector
from app.ingestion.extractors import ExtractionResult, extractor_registry
from app.ingestion.models import DocumentChunk, DocumentImage, DocumentTable
from app.ingestion.ocr import ocr_processor
from app.ingestion.repository import (
    DocumentChunkRepository,
    DocumentImageRepository,
    DocumentRepository,
    DocumentTableRepository,
    DocumentVersionRepository,
    IngestionJobRepository,
)
from app.storage import StorageProvider

logger = get_logger(__name__)


class IngestionPipeline:
    """Coordinates document ingestion — all file operations through StorageProvider.

    Args:
        db: Async database session.
        storage: Pluggable storage provider (local, S3, Azure, GCS, etc.).
    """

    def __init__(self, db: AsyncSession, storage: StorageProvider) -> None:
        self.db = db
        self.storage = storage
        self.doc_repo = DocumentRepository(db)
        self.version_repo = DocumentVersionRepository(db)
        self.chunk_repo = DocumentChunkRepository(db)
        self.table_repo = DocumentTableRepository(db)
        self.image_repo = DocumentImageRepository(db)
        self.job_repo = IngestionJobRepository(db)
        self.cleaner = create_default_pipeline()
        self.start_time: float = 0.0

    async def run(
        self, document_id: str, file_path: str, mime_type: str, user_id: str = "system",
    ) -> dict[str, Any]:
        self.start_time = time.monotonic()
        job = await self.job_repo.get_job_by_document(document_id)
        if not job:
            raise ValueError(f"No ingestion job found for document {document_id}")

        stats: dict[str, Any] = {"ocr_used": False, "page_count": 0, "table_count": 0, "image_count": 0, "chunk_count": 0, "errors": [], "language": None}

        try:
            await self.job_repo.mark_started(job.id)

            # Resolve local file path for third-party extraction libraries
            local_path = self.storage.get_local_path(file_path)

            # Stage 1: Extract
            await self._update_stage(job, "extracting", 10)
            extractor_cls = extractor_registry.get_extractor(mime_type)
            if extractor_cls is None:
                raise ValueError(f"No extractor found for MIME type: {mime_type}")
            result = await extractor_cls(local_path).extract()

            # Stage 2: OCR check
            await self._update_stage(job, "ocr_check", 25)
            needs_ocr = await extractor_cls(local_path).detect_needs_ocr()
            if needs_ocr:
                logger.info("OCR required for document", document_id=document_id)
                ocr_text, ocr_applied = await ocr_processor.process_full_pdf(local_path)
                for page_num, ocr_content in ocr_text.items():
                    if ocr_content.strip():
                        if page_num <= len(result.pages):
                            result.pages[page_num - 1].text = ocr_content
                        else:
                            result.pages.append(type('Page', (), {'page_number': page_num, 'text': ocr_content, 'section_title': None})())
                stats["ocr_used"] = ocr_applied
                result.metadata["ocr_applied"] = True

            # Stage 3: Clean
            await self._update_stage(job, "cleaning", 40)
            cleaned_text = await self.cleaner.clean(result.text, result.metadata)

            # Stage 4: Language detection
            await self._update_stage(job, "detecting_language", 50)
            lang_code, _ = await language_detector.detect(cleaned_text)
            stats["language"] = lang_code

            # Stage 5: Chunking
            await self._update_stage(job, "chunking", 60)
            chunks = await chunking_pipeline.chunk_document(cleaned_text, strategy="auto", mime_type=mime_type)

            # Stage 6: Batch store
            await self._update_stage(job, "storing", 75)
            await self._batch_store(document_id, result, chunks, lang_code)

            # Stage 7: Update document
            stats.update(page_count=len(result.pages), table_count=len(result.tables), image_count=len(result.images), chunk_count=len(chunks))
            processing_time = int((time.monotonic() - self.start_time) * 1000)
            await self.doc_repo.update(document_id, status="completed", language=lang_code, page_count=stats["page_count"], table_count=stats["table_count"], image_count=stats["image_count"], chunk_count=stats["chunk_count"], ocr_used=stats["ocr_used"], processing_time_ms=processing_time, custom_metadata=result.metadata, extraction_errors=result.errors)
            await self.job_repo.mark_completed(job.id)

        except Exception as e:
            logger.exception("Ingestion pipeline failed", document_id=document_id)
            await self.job_repo.mark_failed(job.id, str(e))
            await self.doc_repo.update_status(document_id, "failed")
            stats["errors"].append(str(e))
            raise

        return stats

    async def _update_stage(self, job: Any, stage: str, progress: float) -> None:
        await self.job_repo.update_progress(job.id, progress, stage)

    async def _batch_store(self, document_id: str, result: ExtractionResult, chunks: list, language: str | None) -> None:
        """Batch insert all extraction results — image storage uses StorageProvider."""
        # Batch tables
        table_records = []
        for table in result.tables:
            table_records.append(DocumentTable(
                document_id=document_id, page_number=table.page_number, table_index=table.table_index,
                caption=table.caption, csv_representation=table.to_csv(), html_representation=table.to_html(),
                row_count=table.row_count, column_count=table.column_count,
            ))
        self.db.add_all(table_records)

        # Batch chunks
        chunk_records = []
        for chunk in chunks:
            chunk_records.append(DocumentChunk(
                document_id=document_id, chunk_index=chunk.chunk_index, content=chunk.content,
                content_checksum=chunk.content_checksum, page_number=chunk.page_number,
                section_title=chunk.section_title, section_hierarchy=chunk.section_hierarchy,
                chunk_type=chunk.chunk_type, custom_metadata=chunk.metadata, language=chunk.language or language,
                token_count=chunk.token_count, char_count=chunk.char_count,
            ))
        self.db.add_all(chunk_records)

        # Store images via StorageProvider
        image_dir = await self.storage.generate_storage_path("images", document_id)
        image_records = []
        for img in result.images:
            ext = img.format or "png"
            image_filename = f"page{img.page_number or 0}_img{img.image_index}.{ext}"
            image_path = f"{image_dir}/{image_filename}"
            await self.storage.save(image_path, img.image_data)
            image_records.append(DocumentImage(
                document_id=document_id, page_number=img.page_number, image_index=img.image_index,
                image_path=image_path, caption=img.caption, alt_text=img.alt_text,
                width=img.width, height=img.height, format=img.format, size_bytes=img.size_bytes,
            ))
        self.db.add_all(image_records)
        await self.db.flush()


async def compute_checksum(file_path: str, storage: StorageProvider | None = None) -> str:
    """Compute SHA-256 checksum of a file via StorageProvider, or return empty."""
    if storage:
        return await storage.checksum(file_path)
    return ""


async def validate_file(file_path: str, mime_type: str, storage: StorageProvider, max_size_mb: int | None = None) -> list[str]:
    """Validate a file via StorageProvider — no direct filesystem access."""
    from app.core.config import settings

    errors: list[str] = []
    max_size = (max_size_mb or settings.MAX_UPLOAD_SIZE_MB) * 1024 * 1024

    exists = await storage.exists(file_path)
    if not exists:
        errors.append("File does not exist")
        return errors

    file_size = await storage.size(file_path)
    if file_size == 0:
        errors.append("File is empty")
    if file_size > max_size:
        errors.append(f"File size exceeds maximum of {max_size_mb or settings.MAX_UPLOAD_SIZE_MB}MB")

    if mime_type not in extractor_registry.supported_mime_types:
        errors.append(f"Unsupported MIME type: {mime_type}")

    # Check file header for corruption (read first 4 bytes)
    try:
        header = await storage.read(file_path)
        if len(header) < 4:
            errors.append("File appears corrupt (empty header)")
    except Exception as e:
        errors.append(f"Cannot read file: {e}")

    return errors
