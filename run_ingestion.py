"""Run ingestion pipeline directly — bypasses ARQ worker."""
import asyncio
import sys


async def run_pipeline(document_id: str, mime_type: str):
    from app.db.session import async_session_factory
    from app.storage.factory import get_storage_provider
    from app.ingestion.pipeline import IngestionPipeline
    from app.ingestion.repository import (
        DocumentRepository,
        IngestionJobRepository,
    )

    print(f"🔧 Running ingestion pipeline for document: {document_id}")
    print(f"   MIME type: {mime_type}")

    async with async_session_factory() as db:
        storage = await get_storage_provider()

        # Verify document exists
        doc_repo = DocumentRepository(db)
        doc = await doc_repo.get_by_id(document_id)
        if doc is None:
            print(f"❌ ERROR: Document {document_id} not found")
            return False

        print(f"📄 Document: {doc.original_filename}")
        print(f"   Status: {doc.status}")
        print(f"   MIME: {doc.mime_type}")

        # Verify job exists
        job_repo = IngestionJobRepository(db)
        job = await job_repo.get_job_by_document(document_id)
        if job is None:
            print(f"❌ ERROR: No ingestion job found for document {document_id}")
            return False

        print(f"📋 Job: {job.id} (status: {job.status})")

        # File was moved to documents/{id} during upload
        file_path = f"documents/{document_id}"

        # Run the pipeline
        pipeline = IngestionPipeline(db, storage)
        stats = await pipeline.run(
            document_id=document_id,
            file_path=file_path,
            mime_type=mime_type,
            user_id=doc.user_id or "system",
        )

        # Commit all changes
        await db.commit()

        print(f"\n✅ Pipeline completed successfully!")
        print(f"   Chunks: {stats.get('chunk_count', 0)}")
        print(f"   Pages: {stats.get('page_count', 0)}")
        print(f"   Language: {stats.get('language', 'unknown')}")
        print(f"   OCR: {stats.get('ocr_used', False)}")
        print(f"   Tables: {stats.get('table_count', 0)}")
        print(f"   Images: {stats.get('image_count', 0)}")
        print(f"   Errors: {stats.get('errors', [])}")
        return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_ingestion.py <document_id> [mime_type]")
        sys.exit(1)

    doc_id = sys.argv[1]
    mime_type = sys.argv[2] if len(sys.argv) > 2 else "application/pdf"

    success = asyncio.run(run_pipeline(doc_id, mime_type))
    sys.exit(0 if success else 1)
