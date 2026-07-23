"""Intelligent document chunking strategies.

Implements multiple chunking strategies beyond simple text splitting:
- Semantic chunking (sentence-boundary aware)
- Heading-aware chunking (section-based)
- Markdown-aware chunking (MD heading boundaries)
- Table-aware chunking (preserves table integrity)
- Adaptive chunk sizing (content-density aware)
- Parent-child chunking (hierarchical chunks)
"""

import hashlib
import re
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


class ChunkResult:
    """Result of chunking with metadata for each chunk."""

    def __init__(
        self,
        content: str,
        chunk_index: int,
        chunk_type: str = "text",
        page_number: int | None = None,
        section_title: str | None = None,
        section_hierarchy: list[str] | None = None,
        parent_chunk_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        language: str | None = None,
    ) -> None:
        self.content = content
        self.chunk_index = chunk_index
        self.chunk_type = chunk_type
        self.page_number = page_number
        self.section_title = section_title
        self.section_hierarchy = section_hierarchy or []
        self.parent_chunk_id = parent_chunk_id
        self.metadata = metadata or {}
        self.language = language

    @property
    def content_checksum(self) -> str:
        return hashlib.sha256(
            self.content.encode("utf-8")
        ).hexdigest()

    @property
    def char_count(self) -> int:
        return len(self.content)

    @property
    def token_count(self) -> int:
        """Approximate token count (4 chars per token)."""
        return len(self.content) // 4


class ChunkingStrategy:
    """Base class for chunking strategies."""

    def __init__(
        self,
        max_chunk_size: int = 1024,
        min_chunk_size: int = 100,
        overlap: int = 100,
    ) -> None:
        self.max_chunk_size = max_chunk_size
        self.min_chunk_size = min_chunk_size
        self.overlap = overlap

    async def chunk(
        self,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[ChunkResult]:
        """Chunk the text. Override in subclasses."""
        raise NotImplementedError


class SemanticChunker(ChunkingStrategy):
    """Chunks at sentence boundaries using semantic coherence."""

    async def chunk(
        self,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[ChunkResult]:
        """Chunk text by grouping sentences until size limits are reached."""
        sentences = self._split_sentences(text)
        if not sentences:
            return []

        chunks: list[ChunkResult] = []
        current_chunk: list[str] = []
        current_size = 0

        for sentence in sentences:
            sentence_size = len(sentence)

            if current_size + sentence_size > self.max_chunk_size and current_chunk:
                chunks.append(self._make_chunk(current_chunk, len(chunks), metadata))
                # Add overlap from previous chunk
                overlap_text = self._get_overlap(current_chunk)
                current_chunk = [overlap_text] if overlap_text else []
                current_size = len(overlap_text)

            current_chunk.append(sentence)
            current_size += sentence_size

        if current_chunk:
            chunks.append(self._make_chunk(current_chunk, len(chunks), metadata))

        return chunks

    def _split_sentences(self, text: str) -> list[str]:
        """Split text into sentences."""
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
        return [s.strip() for s in sentences if s.strip()]

    def _make_chunk(
        self,
        sentences: list[str],
        index: int,
        metadata: dict[str, Any] | None = None,
    ) -> ChunkResult:
        content = " ".join(sentences)
        return ChunkResult(
            content=content,
            chunk_index=index,
            chunk_type="semantic",
            metadata=metadata or {},
        )

    def _get_overlap(self, chunk: list[str]) -> str:
        """Get overlap text from the end of a chunk."""
        overlap_size = 0
        overlap_sentences: list[str] = []
        for sentence in reversed(chunk):
            if overlap_size + len(sentence) > self.overlap:
                break
            overlap_sentences.insert(0, sentence)
            overlap_size += len(sentence)
        return " ".join(overlap_sentences)


class HeadingAwareChunker(ChunkingStrategy):
    """Chunks by document headings/sections."""

    async def chunk(
        self,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[ChunkResult]:
        """Split by headings, respecting section boundaries."""
        sections = self._split_by_headings(text)
        chunks: list[ChunkResult] = []

        for idx, (heading, body) in enumerate(sections):
            if not body.strip():
                continue

            # If section is too large, sub-chunk it
            if len(body) > self.max_chunk_size:
                sub_chunker = SemanticChunker(
                    max_chunk_size=self.max_chunk_size,
                    min_chunk_size=self.min_chunk_size,
                )
                sub_chunks = await sub_chunker.chunk(body, metadata)
                for sub in sub_chunks:
                    sub.section_title = heading
                    sub.chunk_type = "section"
                    chunks.append(sub)
            else:
                chunks.append(
                    ChunkResult(
                        content=body,
                        chunk_index=idx,
                        chunk_type="section",
                        section_title=heading,
                        metadata=metadata or {},
                    )
                )

        return chunks

    def _split_by_headings(
        self, text: str
    ) -> list[tuple[str | None, str]]:
        """Split text by heading patterns."""
        heading_pattern = re.compile(
            r"^(#{1,4}\s+.+|.+[^\n]+\n[=-]+)$", re.MULTILINE
        )
        sections: list[tuple[str | None, str]] = []
        parts = heading_pattern.split(text)

        if parts[0].strip():
            sections.append((None, parts[0].strip()))

        for i in range(1, len(parts) - 1, 2):
            heading = parts[i].strip() if i < len(parts) else None
            body = parts[i + 1].strip() if i + 1 < len(parts) else ""
            sections.append((heading, body))

        return sections


class MarkdownAwareChunker(ChunkingStrategy):
    """Chunks preserving markdown structure."""

    async def chunk(
        self,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[ChunkResult]:
        """Chunk markdown text by headings, keeping code blocks intact."""
        lines = text.split("\n")
        chunks: list[ChunkResult] = []
        current_lines: list[str] = []
        current_size = 0
        current_heading: str | None = None
        in_code_block = False

        for line in lines:
            # Track code blocks
            if line.strip().startswith("```"):
                in_code_block = not in_code_block

            # New heading (outside code block)
            heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if heading_match and not in_code_block:
                # Flush current section
                if current_lines and current_size >= self.min_chunk_size:
                    chunks.append(
                        ChunkResult(
                            content="\n".join(current_lines),
                            chunk_index=len(chunks),
                            chunk_type="markdown_section",
                            section_title=current_heading,
                            metadata=metadata or {},
                        )
                    )
                    current_lines = []
                    current_size = 0

                current_heading = heading_match.group(2)

            current_lines.append(line)
            current_size += len(line)

        # Flush remaining
        if current_lines:
            chunks.append(
                ChunkResult(
                    content="\n".join(current_lines),
                    chunk_index=len(chunks),
                    chunk_type="markdown_section",
                    section_title=current_heading,
                    metadata=metadata or {},
                )
            )

        return chunks


class TableAwareChunker(ChunkingStrategy):
    """Chunks keeping tables intact as separate chunks."""

    async def chunk(
        self,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[ChunkResult]:
        """Split text, preserving tables as atomic chunks."""
        lines = text.split("\n")
        chunks: list[ChunkResult] = []
        current_text: list[str] = []
        in_table = False
        table_lines: list[str] = []

        for line in lines:
            is_table_line = (
                "|" in line
                and line.strip().startswith("|")
                and line.strip().endswith("|")
            )

            if is_table_line:
                if current_text:
                    chunks.append(
                        ChunkResult(
                            content="\n".join(current_text),
                            chunk_index=len(chunks),
                            chunk_type="text",
                            metadata=metadata or {},
                        )
                    )
                    current_text = []
                table_lines.append(line)
                in_table = True
            else:
                if in_table and table_lines:
                    chunks.append(
                        ChunkResult(
                            content="\n".join(table_lines),
                            chunk_index=len(chunks),
                            chunk_type="table",
                            metadata=metadata or {},
                        )
                    )
                    table_lines = []
                    in_table = False
                current_text.append(line)

        # Flush remaining
        if table_lines:
            chunks.append(
                ChunkResult(
                    content="\n".join(table_lines),
                    chunk_index=len(chunks),
                    chunk_type="table",
                    metadata=metadata or {},
                )
            )
        elif current_text:
            chunks.append(
                ChunkResult(
                    content="\n".join(current_text),
                    chunk_index=len(chunks),
                    chunk_type="text",
                    metadata=metadata or {},
                )
            )

        return chunks


class AdaptiveChunker(ChunkingStrategy):
    """Adjusts chunk size based on content density.

    Dense content (code, tables) gets smaller chunks.
    Sparse content (narrative text) gets larger chunks.
    """

    DENSE_PATTERNS = [
        re.compile(r"^\s{4,}\S"),  # Indented code
        re.compile(r"^\|.+\|$"),  # Table rows
        re.compile(r"^\d+[.\)]\s+\S"),  # Numbered lists
        re.compile(r"^-\s+\S"),  # Bullet lists
    ]

    async def chunk(
        self,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[ChunkResult]:
        """Chunk with adaptive sizing based on content density."""
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks: list[ChunkResult] = []
        current_chunk: list[str] = []
        current_size = 0

        for paragraph in paragraphs:
            density = self._measure_density(paragraph)
            adaptive_max = int(self.max_chunk_size * density)

            if current_size + len(paragraph) > adaptive_max and current_chunk:
                chunks.append(
                    ChunkResult(
                        content="\n\n".join(current_chunk),
                        chunk_index=len(chunks),
                        chunk_type="adaptive",
                        metadata=metadata or {},
                    )
                )
                current_chunk = []
                current_size = 0

            current_chunk.append(paragraph)
            current_size += len(paragraph)

        if current_chunk:
            chunks.append(
                ChunkResult(
                    content="\n\n".join(current_chunk),
                    chunk_index=len(chunks),
                    chunk_type="adaptive",
                    metadata=metadata or {},
                )
            )

        return chunks

    def _measure_density(self, text: str) -> float:
        """Measure content density (0.3 = dense, 1.0 = sparse)."""
        if not text:
            return 1.0

        dense_line_count = 0
        lines = text.split("\n")
        for line in lines:
            for pattern in self.DENSE_PATTERNS:
                if pattern.match(line):
                    dense_line_count += 1
                    break

        ratio = dense_line_count / len(lines) if lines else 0
        # Dense content gets smaller chunks (lower density value)
        return max(0.3, 1.0 - (ratio * 0.7))


class ParentChildChunker(ChunkingStrategy):
    """Creates hierarchical parent-child chunk relationships.

    Large parent chunks (for context) with smaller child chunks (for precision).
    """

    def __init__(
        self,
        parent_chunk_size: int = 2048,
        child_chunk_size: int = 512,
        child_overlap: int = 50,
    ) -> None:
        super().__init__(
            max_chunk_size=parent_chunk_size,
            min_chunk_size=100,
            overlap=0,
        )
        self.parent_chunk_size = parent_chunk_size
        self.child_chunk_size = child_chunk_size
        self.child_overlap = child_overlap

    async def chunk(
        self,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[ChunkResult]:
        """Create parent and child chunks."""
        meta = metadata or {}

        # Create parent chunks using heading-aware splitting
        heading_chunker = HeadingAwareChunker(
            max_chunk_size=self.parent_chunk_size,
        )
        parent_chunks = await heading_chunker.chunk(text, meta)

        all_chunks: list[ChunkResult] = []
        for parent in parent_chunks:
            all_chunks.append(parent)

            # Create child chunks from parent content
            child_chunker = SemanticChunker(
                max_chunk_size=self.child_chunk_size,
                overlap=self.child_overlap,
            )
            children = await child_chunker.chunk(parent.content, meta)

            # To avoid self-referencing, assign parent IDs after
            for child in children:
                child.parent_chunk_id = "PENDING_PARENT"  # Resolved after save
                child.chunk_type = "child"
                child.section_title = parent.section_title
                all_chunks.append(child)

        # Assign parent_chunk_id using parent chunk index
        parent_idx = 0
        for i, chunk in enumerate(all_chunks):
            if chunk.chunk_type in ("section", "text"):
                parent_idx = i
            elif chunk.parent_chunk_id == "PENDING_PARENT":
                chunk.parent_chunk_id = all_chunks[parent_idx].content_checksum

        return all_chunks


class ChunkingPipeline:
    """Orchestrates multiple chunking strategies."""

    def __init__(self) -> None:
        self.strategies: dict[str, ChunkingStrategy] = {
            "semantic": SemanticChunker(),
            "heading": HeadingAwareChunker(),
            "markdown": MarkdownAwareChunker(),
            "table_aware": TableAwareChunker(),
            "adaptive": AdaptiveChunker(),
            "parent_child": ParentChildChunker(),
        }

    async def chunk_document(
        self,
        text: str,
        strategy: str = "adaptive",
        metadata: dict[str, Any] | None = None,
        mime_type: str | None = None,
    ) -> list[ChunkResult]:
        """Chunk document using the specified strategy.

        Auto-selects strategy based on MIME type if not specified.
        """
        if strategy == "auto" and mime_type:
            strategy = self._auto_select_strategy(mime_type)

        chunker = self.strategies.get(strategy)
        if chunker is None:
            logger.warning(
                "Unknown chunking strategy, falling back to adaptive",
                strategy=strategy,
            )
            chunker = self.strategies["adaptive"]

        return await chunker.chunk(text, metadata)

    def _auto_select_strategy(self, mime_type: str) -> str:
        """Auto-select chunking strategy based on document type."""
        strategy_map = {
            "text/markdown": "markdown",
            "text/csv": "table_aware",
            "text/html": "heading",
            "application/pdf": "adaptive",
            "application/json": "adaptive",
        }
        return strategy_map.get(mime_type, "adaptive")


chunking_pipeline = ChunkingPipeline()
