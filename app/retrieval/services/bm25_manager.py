"""BM25 Index Manager — manages the lifecycle of the BM25 inverted index.

Handles building, rebuilding, status tracking, and staleness detection
for the BM25 keyword index. Supports building from DocumentChunkRepository.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.logging import get_logger
from app.ingestion.repository import DocumentChunkRepository
from app.retrieval.exceptions import BM25IndexError
from app.retrieval.retrievers.bm25 import BM25Retriever
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


class BM25IndexManager:
    """Manages the BM25 inverted index lifecycle.

    Tracks index state (built, stale, last_built_at, doc_count) and
    supports building from the DocumentChunkRepository.

    Usage:
        manager = BM25IndexManager(bm25_retriever)
        await manager.build_from_repository(db)
        status = await manager.get_status()
    """

    def __init__(self, bm25_retriever: BM25Retriever) -> None:
        self._retriever = bm25_retriever
        self._last_built_at: datetime | None = None
        self._total_chunks_loaded: int = 0
        self._build_error: str | None = None

    async def build_from_repository(
        self,
        db: AsyncSession,
        collection_name: str | None = None,
    ) -> dict[str, Any]:
        """Build the BM25 index from ingested document chunks.

        Loads all chunks from DocumentChunkRepository and builds
        the BM25 inverted index.

        Args:
            db: Database session.
            collection_name: Optional collection name (unused, reserved).

        Returns:
            Dict with build stats (total_docs, unique_tokens, avg_doc_length).

        Raises:
            BM25IndexError: If building fails.
        """
        try:
            chunk_repo = DocumentChunkRepository(db)
            # Load all chunks across all documents
            # Use a list of all documents
            from app.ingestion.repository import DocumentRepository

            doc_repo = DocumentRepository(db)
            docs, total = await doc_repo.list_documents(page=1, size=10000, include_deleted=False)

            all_chunks: list[dict[str, Any]] = []
            for doc in docs:
                chunks = await chunk_repo.get_chunks_by_document(doc.id)
                for c in chunks:
                    meta = dict(c.custom_metadata) if c.custom_metadata else {}
                    meta["document_title"] = doc.title or doc.original_filename
                    meta["source"] = doc.original_filename
                    all_chunks.append(
                        {
                            "chunk_id": c.id,
                            "document_id": c.document_id,
                            "text": c.content,
                            "metadata": meta,
                            "checksum": c.content_checksum,
                            "chunk_index": c.chunk_index,
                            "page_number": c.page_number,
                            "section_title": c.section_title,
                            "language": c.language or "unknown",
                        }
                    )

            if not all_chunks:
                logger.warning("No chunks found to build BM25 index")
                return {"total_docs": 0, "unique_tokens": 0, "avg_doc_length": 0.0}

            await self._retriever.build_index(all_chunks)
            self._last_built_at = datetime.now(timezone.utc)
            self._total_chunks_loaded = len(all_chunks)
            self._build_error = None

            logger.info(
                "BM25 index built from repository",
                total_chunks=len(all_chunks),
                total_docs=self._retriever.index_size,
                last_built=self._last_built_at.isoformat(),
            )

            return {
                "total_docs": self._retriever.index_size,
                "unique_tokens": (
                    len(self._retriever._doc_freqs) if hasattr(self._retriever, "_doc_freqs") else 0
                ),
                "avg_doc_length": (
                    round(self._retriever._avg_doc_length, 1)
                    if hasattr(self._retriever, "_avg_doc_length")
                    else 0.0
                ),
                "total_chunks_loaded": self._total_chunks_loaded,
            }

        except Exception as e:
            self._build_error = str(e)
            logger.exception("Failed to build BM25 index from repository")
            raise BM25IndexError(f"Failed to build BM25 index from repository: {e}")

    async def rebuild(self, db: AsyncSession) -> dict[str, Any]:
        """Rebuild the BM25 index from scratch.

        Resets the existing index and rebuilds from the repository.

        Args:
            db: Database session.

        Returns:
            Build stats dict.
        """
        # Reset existing index
        self._retriever._entries = []
        self._retriever._doc_freqs = {}
        self._retriever._avg_doc_length = 0.0
        self._retriever._index_built = False
        self._retriever._total_docs = 0

        return await self.build_from_repository(db)

    async def clear(self) -> None:
        """Clear the BM25 index entirely."""
        self._retriever._entries = []
        self._retriever._doc_freqs = {}
        self._retriever._avg_doc_length = 0.0
        self._retriever._index_built = False
        self._retriever._total_docs = 0
        self._last_built_at = None
        self._total_chunks_loaded = 0
        logger.info("BM25 index cleared")

    async def get_status(self) -> dict[str, Any]:
        """Get the current status of the BM25 index.

        Returns:
            Dict with built status, doc count, last built time, and staleness info.
        """
        now = datetime.now(timezone.utc)
        return {
            "index_built": self._retriever.is_index_built,
            "total_docs": self._retriever.index_size,
            "last_built_at": self._last_built_at.isoformat() if self._last_built_at else None,
            "seconds_since_built": (
                (now - self._last_built_at).total_seconds() if self._last_built_at else None
            ),
            "total_chunks_loaded": self._total_chunks_loaded,
            "build_error": self._build_error,
            "healthy": self._retriever.is_index_built and self._build_error is None,
        }

    @property
    def retriever(self) -> BM25Retriever:
        """Get the managed BM25 retriever."""
        return self._retriever

    @property
    def is_ready(self) -> bool:
        """Check if the BM25 index is built and ready for retrieval."""
        return self._retriever.is_index_built and self._build_error is None
