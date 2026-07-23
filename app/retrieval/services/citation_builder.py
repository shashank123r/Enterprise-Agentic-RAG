"""Citation builder — generates structured citations from retrieved chunks.

Every retrieved chunk gets a citation containing:
- document_id
- document_title (from metadata)
- chunk_id
- page number
- section title
- retrieval score
- retrieval method (dense, bm25, hybrid, reranked)
- source (document filename/URL)
"""

from __future__ import annotations

from typing import Any

from app.retrieval.schemas import Citation, RetrievedChunk


class CitationBuilder:
    """Builds structured citations from retrieved chunks.

    Usage:
        builder = CitationBuilder()
        citations = builder.build(chunks)
    """

    def build(
        self,
        chunks: list[RetrievedChunk],
    ) -> list[Citation]:
        """Build citations for all retrieved chunks.

        Args:
            chunks: List of RetrievedChunk after de-duplication and context building.

        Returns:
            List of Citation objects, each referencing a unique chunk.
        """
        seen: set[str] = set()
        citations: list[Citation] = []

        for chunk in chunks:
            if chunk.chunk_id in seen:
                continue
            seen.add(chunk.chunk_id)

            # Extract document title from metadata
            metadata = chunk.metadata or {}
            doc_title = (
                metadata.get("document_title")
                or metadata.get("title")
                or metadata.get("filename")
                or ""
            )
            source = (
                metadata.get("source")
                or metadata.get("filename")
                or chunk.metadata.get("original_filename", "")
                if isinstance(chunk.metadata, dict)
                else ""
            )

            citations.append(
                Citation(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    document_title=doc_title,
                    source=source,
                    retrieval_method=chunk.retrieval_source,
                    text_preview=chunk.text[:200],
                    page_number=chunk.page_number,
                    section_title=chunk.section_title,
                    score=chunk.score,
                    rerank_score=chunk.rerank_score,
                )
            )

        return citations

    def format_as_text(self, citations: list[Citation]) -> str:
        """Format citations as readable text for inclusion in prompts.

        Args:
            citations: List of Citation objects.

        Returns:
            Formatted citation text.
        """
        lines = ["\n## References"]
        for idx, c in enumerate(citations, 1):
            parts = [f"[{idx}]"]
            if c.document_title:
                parts.append(c.document_title)
            if c.section_title:
                parts.append(f"Section: {c.section_title}")
            if c.page_number is not None:
                parts.append(f"Page {c.page_number}")
            parts.append(f"(Score: {c.score:.3f}")
            if c.rerank_score is not None:
                parts[-1] = f"(Rerank: {c.rerank_score:.3f}, Score: {c.score:.3f}"
            parts[-1] += ")"
            parts.append(f"Method: {c.retrieval_method}")
            lines.append(" | ".join(parts))

        return "\n".join(lines)

    def format_as_json(self, citations: list[Citation]) -> list[dict[str, Any]]:
        """Format citations as JSON-serializable dicts.

        Args:
            citations: List of Citation objects.

        Returns:
            List of citation dicts.
        """
        return [
            {
                "chunk_id": c.chunk_id,
                "document_id": c.document_id,
                "document_title": c.document_title,
                "source": c.source,
                "retrieval_method": c.retrieval_method,
                "text_preview": c.text_preview,
                "page_number": c.page_number,
                "section_title": c.section_title,
                "score": c.score,
                "rerank_score": c.rerank_score,
            }
            for c in citations
        ]
