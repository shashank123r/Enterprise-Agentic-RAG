"""High-performance batch indexer.

Splits large chunk sets into configurable batches, processes them
with controlled concurrency, handles partial failures, and supports
checkpointing for resume-after-crash recovery.

The BatchIndexer contains orchestration ONLY — it delegates embedding
to EmbeddingProvider and storage to VectorStore.
"""

import asyncio
import time
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.embeddings.cache import EmbeddingCacheService
from app.embeddings.providers.base import EmbeddingProvider
from app.vector_stores.base import VectorRecord, VectorStore
from app.embeddings.exceptions import DuplicateInputIdError, EmbeddingError, UnsupportedLanguageError
from app.vector_stores.exceptions import VectorDimensionMismatch, BatchInsertError

logger = get_logger(__name__)


class BatchIndexer:
    """Splits chunks into batches and indexes them with concurrency control.

    Usage::
        indexer = BatchIndexer(
            embedding_provider=provider,
            vector_store=store,
            cache=cache_service,
            batch_size=32,
            max_concurrent=5,
            embedding_model="nvidia/nv-embed-qa-4",
        )

        results = await indexer.index_chunks(
            collection_name="docs",
            chunks=[...],
            document_id="doc-123",
            embedding_model="nvidia/nv-embed-qa-4",
            cancel_event=cancel_event,
        )
    """

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
        cache: EmbeddingCacheService | None = None,
        batch_size: int = 32,
        max_concurrent: int = 5,
        embedding_model: str = "nvidia/nv-embed-qa-4",
        milvus_batch_size: int = 100,
    ) -> None:
        self._provider = embedding_provider
        self._store = vector_store
        self._cache = cache
        self._batch_size = min(batch_size, settings.EMBEDDING_BATCH_SIZE)
        self._max_concurrent = max_concurrent or settings.MAX_CONCURRENT_REQUESTS
        self._embedding_model = embedding_model
        self._milvus_batch_size = milvus_batch_size
        self._semaphore = asyncio.Semaphore(self._max_concurrent)
        self._dimension: int | None = None

    async def index_chunks(
        self,
        collection_name: str,
        chunks: list[dict[str, Any]],
        document_id: str,
        cache_hits: list[int] | None = None,
        progress_callback: Any = None,
        cancel_event: asyncio.Event | None = None,
    ) -> dict[str, Any]:
        """Index a list of chunks into the vector store.

        Pipeline per batch:
            1. Compute checksum (cache lookup if available)
            2. Embed via provider (or cache hit)
            3. Build VectorRecord
            4. Upsert into Milvus
            5. Report progress

        Args:
            collection_name: Target Milvus collection.
            chunks: List of chunk dicts (must have 'text', 'metadata', 'chunk_id', etc.).
            document_id: Parent document ID.
            cache_hits: Mutable list to append hit indices to.
            progress_callback: Optional async callable(processed, total, failed).
            cancel_event: If set, stops processing early.

        Returns:
            Dict with 'indexed', 'failed', 'cache_hits', and 'duration_ms'.
        """
        if not chunks:
            return {"indexed": 0, "failed": 0, "cache_hits": 0, "duration_ms": 0.0}

        if cancel_event and cancel_event.is_set():
            logger.warning("Indexing cancelled before starting", document_id=document_id)
            return {"indexed": 0, "failed": 0, "cache_hits": 0, "duration_ms": 0.0, "cancelled": True}

        if self._dimension is None:
            self._dimension = await self._provider.dimension()

        total = len(chunks)
        indexed = 0
        failed = 0
        hit_count = 0
        start_time = time.monotonic()

        # Split chunks into batches
        batches = [
            chunks[i : i + self._batch_size]
            for i in range(0, total, self._batch_size)
        ]

        logger.info(
            "Starting batch indexing",
            document_id=document_id,
            total_chunks=total,
            batches=len(batches),
            batch_size=self._batch_size,
        )

        async def _process_batch(
            batch: list[dict[str, Any]],
            batch_index: int,
        ) -> tuple[int, int, int]:
            """Process a single batch: embed, upsert, report.

            Returns:
                Tuple of (indexed_count, failed_count, cache_hit_count).
            """
            if cancel_event and cancel_event.is_set():
                return (0, len(batch), 0)

            async with self._semaphore:
                return await self._process_single_batch(
                    collection_name=collection_name,
                    batch=batch,
                    document_id=document_id,
                    cache_hits_out=cache_hits,
                )

        # Process batches with concurrency control
        tasks = [
            _process_batch(batch, idx)
            for idx, batch in enumerate(batches)
        ]

        done_count = 0
        for coro in asyncio.as_completed(tasks):
            try:
                b_indexed, b_failed, b_hits = await coro
                indexed += b_indexed
                failed += b_failed
                hit_count += b_hits
                done_count += 1

                if progress_callback is not None:
                    await progress_callback(indexed + failed, total, failed)

            except asyncio.CancelledError:
                logger.warning("Batch indexing cancelled mid-flight", document_id=document_id)
                raise
            except Exception as e:
                logger.error("Unexpected batch error", error=str(e))
                failed += 1
                done_count += 1

        duration_ms = (time.monotonic() - start_time) * 1000

        logger.info(
            "Batch indexing complete",
            document_id=document_id,
            indexed=indexed,
            failed=failed,
            cache_hits=hit_count,
            duration_ms=round(duration_ms, 1),
        )

        return {
            "indexed": indexed,
            "failed": failed,
            "cache_hits": hit_count,
            "duration_ms": round(duration_ms, 1),
        }

    async def _process_single_batch(
        self,
        collection_name: str,
        batch: list[dict[str, Any]],
        document_id: str,
        cache_hits_out: list[int] | None = None,
    ) -> tuple[int, int, int]:
        """Embed, validate, and upsert a single batch of chunks.

        Returns:
            Tuple of (indexed_count, failed_count, cache_hit_count).
        """
        texts = [c.get("text", "") for c in batch]
        checksums = [c.get("checksum", "") for c in batch]

        # Step 1: Check cache
        vectors: list[list[float] | None] = [None] * len(batch)
        cache_hits = 0

        if self._cache is not None and self._cache.enabled:
            cached = await self._cache.get_batch(
                checksums, self._embedding_model, self._dimension or 0,
            )
            for idx, vec in cached.items():
                vectors[idx] = vec
                cache_hits += 1
                if cache_hits_out is not None:
                    cache_hits_out.append(idx)

        # Step 2: Embed uncached chunks
        uncached_indices = [i for i, v in enumerate(vectors) if v is None]
        if uncached_indices:
            uncached_texts = [texts[i] for i in uncached_indices]
            try:
                metadata_list = [batch[i].get("metadata", {}) for i in uncached_indices]
                result = await self._provider.embed_documents(
                    uncached_texts,
                    metadata=metadata_list,
                )

                # Log any embedding provider errors for debugging
                if result.errors:
                    logger.warning(
                        "Embedding provider returned errors",
                        errors=result.errors,
                        failed_count=len(result.failed_indices),
                        total=len(uncached_texts),
                    )

                # Map results back to original indices
                for result_idx, orig_idx in enumerate(uncached_indices):
                    if result_idx in result.failed_indices:
                        continue
                    if result_idx < len(result.vectors):
                        vectors[orig_idx] = result.vectors[result_idx]

                        # Write to cache
                        if self._cache is not None and checksums[orig_idx]:
                            await self._cache.set(
                                checksums[orig_idx],
                                self._embedding_model,
                                self._dimension or 0,
                                result.vectors[result_idx],
                            )

                for fail_idx in result.failed_indices:
                    if fail_idx < len(uncached_indices):
                        vectors[uncached_indices[fail_idx]] = None

            except (DuplicateInputIdError, UnsupportedLanguageError) as e:
                # H2: Validation errors must propagate immediately as request failures.
                # These are not transient batch failures — they indicate invalid inputs
                # that cannot be recovered by retrying.
                logger.error("Validation error during batch embedding", error=str(e))
                raise
            except EmbeddingError as e:
                logger.error("Batch embedding failed", error=str(e), code=e.code)
                for i in uncached_indices:
                    vectors[i] = None
            except Exception as e:
                logger.error("Unexpected batch embedding error", error=str(e))
                for i in uncached_indices:
                    vectors[i] = None



        # Step 3: Build VectorRecords
        records: list[VectorRecord] = []
        failed_count = 0

        for i, chunk in enumerate(batch):
            vec = vectors[i]
            if vec is None:
                failed_count += 1
                continue

            records.append(VectorRecord(
                chunk_id=chunk.get("chunk_id", ""),
                document_id=document_id,
                vector=vec,
                text=chunk.get("text", ""),
                metadata=chunk.get("metadata", {}),
                page_number=chunk.get("page_number"),
                chunk_index=chunk.get("chunk_index", 0),
                section_title=chunk.get("section_title"),
                language=chunk.get("language", "unknown"),
                checksum=chunk.get("checksum", ""),
                version=chunk.get("version", 1),
                source=chunk.get("source", ""),
                embedding_model=self._embedding_model,
            ))

        # Step 4: Upsert into Milvus
        if records:
            try:
                upserted = await self._store.upsert_vectors(
                    collection_name,
                    records,
                    batch_size=self._milvus_batch_size,
                )
                indexed_count = upserted
            except (VectorDimensionMismatch, BatchInsertError) as e:
                logger.error("Vector store upsert failed", error=str(e))
                indexed_count = 0
                failed_count = len(records)
            except Exception as e:
                logger.error("Unexpected upsert error", error=str(e))
                indexed_count = 0
                failed_count = len(records)
        else:
            indexed_count = 0

        return (indexed_count, failed_count, cache_hits)
