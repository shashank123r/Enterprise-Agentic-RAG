"""Context builder — assembles retrieval results into a coherent context window.

Removes duplicates, preserves document order, merges neighboring chunks,
respects token budgets, and preserves citations.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.retrieval.schemas import RetrievalCandidate, RetrievedChunk

logger = get_logger(__name__)

# Rough estimate: 4 characters ≈ 1 token
_CHARS_PER_TOKEN = 4


class ContextBuilder:
    """Builds a context window from retrieved chunks.

    Pipeline:
        1. Remove duplicate chunks (by chunk_id).
        2. Sort by document_id and chunk_index for coherent reading.
        3. Merge neighboring chunks from the same document.
        4. Respect token budget if specified.
        5. Preserve citation metadata for every included chunk.

    Usage:
        builder = ContextBuilder(max_tokens=4096)
        context, chunks, citations = builder.build(retrieved_candidates)
    """

    def __init__(
        self,
        max_tokens: int | None = None,
        respect_order: bool = True,
        merge_neighbors: bool = True,
    ) -> None:
        self._max_tokens = max_tokens
        self._respect_order = respect_order
        self._merge_neighbors = merge_neighbors

    def build(
        self,
        candidates: list[RetrievalCandidate],
        max_tokens: int | None = None,
    ) -> tuple[str, list[RetrievedChunk], list[dict[str, Any]]]:
        """Build context window from retrieved candidates.

        Args:
            candidates: Ranked retrieval candidates.
            max_tokens: Override max tokens. Uses instance default if not set.

        Returns:
            Tuple of (context_text, cleaned_chunks, citation_data_list).
        """
        budget = max_tokens or self._max_tokens

        # Step 1: Deduplicate
        deduped = self._deduplicate(candidates)
        dedup_count = len(candidates) - len(deduped)

        # Step 2: Sort for coherent reading
        if self._respect_order:
            sorted_chunks = self._sort_coherent(deduped)
        else:
            sorted_chunks = deduped

        # Step 3: Merge neighbors
        if self._merge_neighbors:
            merged = self._merge_neighboring(sorted_chunks)
        else:
            merged = sorted_chunks

        # Step 4: Apply token budget
        if budget:
            trimmed, exceeded = self._apply_budget(merged, budget)
        else:
            trimmed = merged
            exceeded = False

        # Step 5: Build context text and citations
        context_parts: list[str] = []
        citations: list[dict[str, Any]] = []
        seen_citations: set[str] = set()

        for idx, chunk in enumerate(trimmed):
            header = f"[Source {idx + 1}]"
            if chunk.section_title:
                header += f" | {chunk.section_title}"
            if chunk.page_number is not None:
                header += f" | Page {chunk.page_number}"

            context_parts.append(f"{header}\n{chunk.text}\n")

            # Build citation entry
            if chunk.chunk_id not in seen_citations:
                citations.append(
                    {
                        "chunk_id": chunk.chunk_id,
                        "document_id": chunk.document_id,
                        "text_preview": chunk.text[:200],
                        "page_number": chunk.page_number,
                        "section_title": chunk.section_title,
                        "score": chunk.score,
                        "rerank_score": chunk.rerank_score,
                    }
                )
                seen_citations.add(chunk.chunk_id)

        # Build RetrievedChunk objects from merged candidates
        retrieved_chunks = [
            RetrievedChunk(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                text=c.text,
                score=c.score,
                rerank_score=c.rerank_score,
                page_number=c.page_number,
                section_title=c.section_title,
                chunk_index=c.chunk_index,
                language=c.language,
                metadata=c.metadata,
                retrieval_source=c.retrieval_source,
            )
            for c in trimmed
        ]

        context_text = "\n".join(context_parts)

        logger.debug(
            "Context built",
            candidates_in=len(candidates),
            dedup_removed=dedup_count,
            merged=len(merged) != len(sorted_chunks),
            trimmed=len(trimmed),
            token_budget=budget,
            context_chars=len(context_text),
        )

        return context_text, retrieved_chunks, citations

    @staticmethod
    def _deduplicate(candidates: list[RetrievalCandidate]) -> list[RetrievalCandidate]:
        """Remove duplicate candidates by chunk_id, keeping highest score.

        Args:
            candidates: List of candidates.

        Returns:
            Deduplicated list.
        """
        seen: dict[str, RetrievalCandidate] = {}
        for c in candidates:
            if c.chunk_id not in seen or c.score > seen[c.chunk_id].score:
                seen[c.chunk_id] = c
        return list(seen.values())

    @staticmethod
    def _sort_coherent(candidates: list[RetrievalCandidate]) -> list[RetrievalCandidate]:
        """Sort candidates for coherent reading — by document then chunk position.

        Args:
            candidates: List of candidates.

        Returns:
            Sorted list.
        """
        return sorted(candidates, key=lambda c: (c.document_id, c.chunk_index))

    @staticmethod
    def _merge_neighboring(candidates: list[RetrievalCandidate]) -> list[RetrievalCandidate]:
        """Merge neighboring chunks from the same document.

        Two chunks are neighbors if they share the same document_id
        and their chunk_index is consecutive.

        Args:
            candidates: Sorted list of candidates.

        Returns:
            List with merged neighbors.
        """
        if not candidates:
            return []

        merged: list[RetrievalCandidate] = []
        current = candidates[0]

        for next_c in candidates[1:]:
            # Check if they're neighbors
            same_doc = current.document_id == next_c.document_id
            consecutive = abs(next_c.chunk_index - current.chunk_index) == 1

            if same_doc and consecutive:
                # Merge: combine text, use higher score
                current.text = f"{current.text}\n\n{next_c.text}"
                current.score = max(current.score, next_c.score)
                if next_c.rerank_score is not None:
                    current.rerank_score = max(current.rerank_score or 0, next_c.rerank_score)
            else:
                merged.append(current)
                current = next_c

        merged.append(current)
        return merged

    @staticmethod
    def _apply_budget(
        candidates: list[RetrievalCandidate],
        max_tokens: int,
    ) -> tuple[list[RetrievalCandidate], bool]:
        """Trim candidates to fit within a token budget.

        Args:
            candidates: List of candidates.
            max_tokens: Maximum token count.

        Returns:
            Tuple of (trimmed_list, exceeded_budget).
        """
        total_chars = 0
        budget_chars = max_tokens * _CHARS_PER_TOKEN
        result: list[RetrievalCandidate] = []

        for c in candidates:
            chunk_chars = len(c.text) + 80  # 80 chars for header overhead
            if total_chars + chunk_chars > budget_chars:
                # Try to include partially if this is the first chunk
                if not result:
                    max_chars = budget_chars - total_chars
                    c.text = c.text[:max_chars] + "..."
                    result.append(c)
                    total_chars += chunk_chars
                break
            result.append(c)
            total_chars += chunk_chars

        exceeded = total_chars > budget_chars
        return result, exceeded
