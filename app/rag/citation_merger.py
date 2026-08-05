"""Citation merger — attaches source metadata to citations in generated answers.

Maps citation numbers in the generated answer to their source chunks
and produces structured citation metadata with document titles, pages,
sections, and scores.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.rag.schemas import CitationInfo
from app.retrieval.schemas import RetrievedChunk

logger = get_logger(__name__)


class CitationMerger:
    """Merges retrieval citations with generated answer citations.

    Maps citation indices used in the LLM response back to their
    original source chunks and produces structured CitationInfo objects.

    Usage:
        merger = CitationMerger()
        citations = merger.build_citations(chunks, citation_nums)
    """

    def build_citations(
        self,
        chunks: list[RetrievedChunk],
        citation_indices: list[int] | None = None,
    ) -> list[CitationInfo]:
        """Build structured citations from retrieved chunks.

        Args:
            chunks: Source chunks used in the RAG pipeline.
            citation_indices: If provided, only include these citation indices (1-based).
                If None, include all chunks.

        Returns:
            List of CitationInfo objects for the response.
        """
        citations: list[CitationInfo] = []
        seen: set[str] = set()

        indices = citation_indices if citation_indices is not None else range(1, len(chunks) + 1)

        for idx in indices:
            chunk_idx = idx - 1  # Convert to 0-based
            if chunk_idx < 0 or chunk_idx >= len(chunks):
                continue

            chunk = chunks[chunk_idx]
            if chunk.chunk_id in seen:
                continue
            seen.add(chunk.chunk_id)

            doc_title = (
                chunk.metadata.get("document_title")
                or chunk.metadata.get("title")
                or f"Document {chunk.document_id[:8]}..."
            )

            source = (
                (chunk.metadata.get("source") or chunk.metadata.get("filename") or "")
                if isinstance(chunk.metadata, dict)
                else ""
            )

            citations.append(
                CitationInfo(
                    index=idx,
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    document_title=doc_title,
                    source=source,
                    retrieval_method=chunk.retrieval_source,
                    page_number=chunk.page_number,
                    section_title=chunk.section_title,
                    text_preview=chunk.text[:300],
                )
            )

        return citations

    def merge_into_answer(
        self,
        answer: str,
        citations: list[CitationInfo],
    ) -> str:
        """Append a references section to the generated answer.

        Args:
            answer: Generated answer text.
            citations: Citation metadata.

        Returns:
            Answer with appended references section.
        """
        if not citations:
            return answer

        refs = ["\n\n## References"]
        for c in citations:
            parts = [f"[{c.index}]"]
            if c.document_title:
                parts.append(c.document_title)
            if c.section_title:
                parts.append(f"Section: {c.section_title}")
            if c.page_number is not None:
                parts.append(f"Page {c.page_number}")
            refs.append(" | ".join(parts))

        return answer + "\n".join(refs)

    def format_citations_for_prompt(self, citations: list[CitationInfo]) -> str:
        """Format citations for inclusion in follow-up prompts.

        Args:
            citations: Citation metadata.

        Returns:
            Formatted citation string for prompt context.
        """
        parts = ["## Referenced Sources"]
        for c in citations:
            location = []
            if c.page_number is not None:
                location.append(f"p. {c.page_number}")
            if c.section_title:
                location.append(c.section_title)
            location_str = f" ({', '.join(location)})" if location else ""

            parts.append(
                f"[{c.index}] {c.document_title}{location_str}: " f'"""{c.text_preview}"""'
            )
        return "\n".join(parts)
