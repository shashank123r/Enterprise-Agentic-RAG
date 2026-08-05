"""Context manager — builds a diverse, token-budgeted context window from retrieved chunks.

Key improvements:
  - Diversity-aware chunk selection (MMR-style: avoids redundant content)
  - Relevance-first selection, then reorder by document position for coherence
  - Accurate token counting via TokenBudget (tiktoken when available)
  - Rich metadata headers (document title, section, page, retrieval method)
  - Per-chunk token accounting with graceful overflow handling
"""

from __future__ import annotations

import re
from typing import Any

from app.core.logging import get_logger
from app.rag.token_budget import TokenBudget
from app.retrieval.schemas import RetrievedChunk

logger = get_logger(__name__)

# Minimum cosine-like overlap to consider two chunks "redundant"
_DIVERSITY_THRESHOLD = 0.85


def _jaccard_sim(a: str, b: str) -> float:
    """Token-level Jaccard similarity for redundancy detection."""
    tok_a = set(re.findall(r"\b\w+\b", a.lower()))
    tok_b = set(re.findall(r"\b\w+\b", b.lower()))
    if not tok_a or not tok_b:
        return 0.0
    return len(tok_a & tok_b) / len(tok_a | tok_b)


class RAGContextManager:
    """Manages the context window for LLM prompt construction.

    Selection pipeline:
        1. Deduplicate by chunk_id (keep highest score)
        2. Diversity filter (MMR-style): drop near-duplicates by content
        3. Relevance-first selection within token budget
        4. Reorder selected chunks by (document_id, chunk_index) for coherence
        5. Format each chunk with rich metadata header

    Usage:
        manager = RAGContextManager()
        context = await manager.build_context(chunks, token_budget)
    """

    def __init__(self, diversity_threshold: float = _DIVERSITY_THRESHOLD) -> None:
        self._diversity_threshold = diversity_threshold

    async def build_context(
        self,
        chunks: list[RetrievedChunk],
        budget: TokenBudget,
    ) -> str:
        """Build a formatted, token-bounded context string.

        Args:
            chunks: Retrieved chunks (may contain duplicates).
            budget: TokenBudget instance for allocation and counting.

        Returns:
            Formatted context string ready for prompt insertion.
        """
        if not chunks:
            return ""

        context_budget = budget.allocate_for_context()

        # ── 1. Deduplicate by chunk_id ─────────────────────────────────────
        seen_ids: dict[str, RetrievedChunk] = {}
        for c in chunks:
            if c.chunk_id not in seen_ids or c.score > seen_ids[c.chunk_id].score:
                seen_ids[c.chunk_id] = c
        unique = list(seen_ids.values())

        # ── 2. Diversity filter ────────────────────────────────────────────
        diverse = self._diversity_filter(unique)

        # ── 3. Relevance-first selection within budget ─────────────────────
        # Sort by score desc; we'll reorder for coherence AFTER selection
        sorted_by_score = sorted(diverse, key=lambda c: c.score, reverse=True)
        selected: list[RetrievedChunk] = []
        used_tokens = 0

        for chunk in sorted_by_score:
            formatted = self._format_chunk(chunk, idx=len(selected) + 1)
            chunk_tokens = budget.count_tokens(formatted)
            if used_tokens + chunk_tokens > context_budget:
                if not selected:
                    # Always include at least one chunk even if over budget
                    trimmed = budget.truncate_to_budget(chunk.text, context_budget - 50)
                    chunk = RetrievedChunk(**{**chunk.model_dump(), "text": trimmed})
                    selected.append(chunk)
                break
            selected.append(chunk)
            used_tokens += chunk_tokens

        # ── 4. Reorder by document position for reading coherence ──────────
        coherent = sorted(selected, key=lambda c: (c.document_id, c.chunk_index))

        # ── 5. Format ──────────────────────────────────────────────────────
        parts = [self._format_chunk(c, idx=i + 1) for i, c in enumerate(coherent)]
        context = "\n".join(parts)

        logger.debug(
            "Context built",
            raw_chunks=len(chunks),
            unique_chunks=len(unique),
            diverse_chunks=len(diverse),
            selected_chunks=len(selected),
            context_tokens=used_tokens,
            budget=context_budget,
        )

        return context

    def _diversity_filter(self, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """Remove near-duplicate chunks using token-level Jaccard similarity."""
        result: list[RetrievedChunk] = []
        for candidate in chunks:
            is_redundant = False
            for accepted in result:
                if _jaccard_sim(candidate.text, accepted.text) >= self._diversity_threshold:
                    is_redundant = True
                    break
            if not is_redundant:
                result.append(candidate)
        return result

    @staticmethod
    def _format_chunk(chunk: RetrievedChunk, idx: int) -> str:
        """Format a single chunk with rich metadata header."""
        doc_title = (
            chunk.metadata.get("document_title")
            or chunk.metadata.get("title")
            or f"Document {chunk.document_id[:8]}"
        )
        header_parts = [f"[Source {idx}]", doc_title]

        if chunk.section_title:
            header_parts.append(f"§ {chunk.section_title}")
        if chunk.page_number is not None:
            header_parts.append(f"p.{chunk.page_number}")
        if chunk.retrieval_source:
            source_label = chunk.retrieval_source.replace("_reranked", "✓")
            header_parts.append(f"[{source_label}]")

        score_label = f"score:{chunk.score:.3f}"
        if chunk.rerank_score is not None:
            score_label = f"rerank:{chunk.rerank_score:.3f}"
        header_parts.append(score_label)

        header = " | ".join(header_parts)
        return f"{header}\n{chunk.text.strip()}\n"

    @staticmethod
    def _section_balance(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """Ensure no single document dominates — cap per-document contributions.

        Internal helper used for very large chunk sets where diversity might
        still be dominated by one document.
        """
        from collections import defaultdict
        doc_counts: dict[str, int] = defaultdict(int)
        balanced: list[RetrievedChunk] = []
        max_per_doc = max(2, len(chunks) // 3)

        for chunk in chunks:
            if doc_counts[chunk.document_id] < max_per_doc:
                balanced.append(chunk)
                doc_counts[chunk.document_id] += 1

        return balanced
