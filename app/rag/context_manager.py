"""Context manager — constructs a coherent context window from retrieved chunks.

Formats chunks with metadata, deduplicates, sorts by document position,
and respects token budgets.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.rag.token_budget import TokenBudget
from app.retrieval.schemas import RetrievedChunk

logger = get_logger(__name__)


class RAGContextManager:
    """Manages the context window for LLM prompt construction.

    Formats retrieved chunks into a structured context section with
    citations, deduplicates content, and enforces token budgets.

    Usage:
        manager = RAGContextManager()
        context = await manager.build_context(chunks, token_budget)
    """

    async def build_context(
        self,
        chunks: list[RetrievedChunk],
        budget: TokenBudget,
    ) -> str:
        """Build a formatted context string from retrieved chunks.

        Pipeline:
            1. Deduplicate chunks by chunk_id
            2. Order by document_id and chunk_index
            3. Format each chunk with metadata headers
            4. Apply token budget

        Args:
            chunks: Retrieved chunks from the retrieval engine.
            budget: TokenBudget instance for allocation.

        Returns:
            Formatted context string ready for prompt insertion.
        """
        if not chunks:
            return ""

        # Step 1: Deduplicate
        seen: dict[str, RetrievedChunk] = {}
        for c in chunks:
            if c.chunk_id not in seen or c.score > seen[c.chunk_id].score:
                seen[c.chunk_id] = c
        unique_chunks = list(seen.values())

        # Step 2: Sort by document then position
        sorted_chunks = sorted(
            unique_chunks, key=lambda c: (c.document_id, c.chunk_index)
        )

        # Step 3: Format each chunk
        context_parts: list[str] = []
        context_tokens = 0
        context_budget = budget.allocate_for_context()

        for idx, chunk in enumerate(sorted_chunks, 1):
            # Build chunk header
            header_parts = [f"[Source {idx}]"]
            doc_title = (
                chunk.metadata.get("document_title")
                or chunk.metadata.get("title")
                or f"Document {chunk.document_id[:8]}..."
            )
            header_parts.append(doc_title)
            if chunk.section_title:
                header_parts.append(f"Section: {chunk.section_title}")
            if chunk.page_number is not None:
                header_parts.append(f"Page {chunk.page_number}")

            # Estimate tokens for this chunk
            chunk_text = f"{' | '.join(header_parts)}\n{chunk.text}\n"
            chunk_tokens = budget.count_tokens(chunk_text)

            # Check budget
            if context_tokens + chunk_tokens > context_budget:
                logger.info(
                    "Context budget reached",
                    chunks_included=idx - 1,
                    total_chunks=len(sorted_chunks),
                    context_tokens=context_tokens,
                    budget=context_budget,
                )
                break

            context_parts.append(chunk_text)
            context_tokens += chunk_tokens

        context = "\n".join(context_parts)

        logger.debug(
            "Context built",
            total_chunks=len(chunks),
            unique_chunks=len(unique_chunks),
            chunks_included=len(context_parts),
            context_tokens=context_tokens,
            budget=context_budget,
        )

        return context
