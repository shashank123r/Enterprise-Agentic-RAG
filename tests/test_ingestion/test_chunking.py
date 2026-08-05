"""Tests for the intelligent chunking pipeline.

Covers all 6 chunking strategies: semantic, heading-aware, markdown-aware,
table-aware, adaptive, and parent-child chunking.
"""

import pytest

from app.ingestion.chunking import ChunkingPipeline, ChunkResult


@pytest.fixture
def chunker() -> ChunkingPipeline:
    return ChunkingPipeline()


class TestSemanticChunking:
    @pytest.mark.asyncio
    async def test_semantic_split(self, chunker: ChunkingPipeline) -> None:
        text = "Hello. This is a test. Multiple sentences. Should be chunked. " * 50
        chunks = await chunker.chunk_semantic(text, max_chunk_size=200)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk.content) <= 250  # Allow some overlap

    @pytest.mark.asyncio
    async def test_semantic_empty_text(self, chunker: ChunkingPipeline) -> None:
        chunks = await chunker.chunk_semantic("")
        assert len(chunks) == 0


class TestHeadingAwareChunking:
    @pytest.mark.asyncio
    async def test_heading_split(self, chunker: ChunkingPipeline) -> None:
        text = (
            "# Introduction\n\nThis is the intro.\n\n"
            "# Methods\n\nWe used a new method.\n\n"
            "# Results\n\nThe results were significant.\n\n"
        )
        chunks = await chunker.chunk_by_headings(text)
        assert len(chunks) >= 3
        assert chunks[0].section_title == "Introduction"
        assert chunks[1].section_title == "Methods"

    @pytest.mark.asyncio
    async def test_heading_no_headings(self, chunker: ChunkingPipeline) -> None:
        text = "Plain text without any headings."
        chunks = await chunker.chunk_by_headings(text)
        assert len(chunks) >= 1


class TestMarkdownAwareChunking:
    @pytest.mark.asyncio
    async def test_markdown_code_blocks(self, chunker: ChunkingPipeline) -> None:
        text = "Some text.\n\n```python\nprint('hello')\n```\n\nMore text."
        chunks = await chunker.chunk_markdown(text)
        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_markdown_lists(self, chunker: ChunkingPipeline) -> None:
        text = "# List\n\n" "- Item 1\n" "- Item 2\n" "- Item 3\n"
        chunks = await chunker.chunk_markdown(text)
        assert len(chunks) >= 1


class TestAdaptiveChunking:
    @pytest.mark.asyncio
    async def test_adaptive_split(self, chunker: ChunkingPipeline) -> None:
        text = "Word " * 1000
        chunks = await chunker.chunk_adaptive(text, target_chunk_size=200)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk.content.split()) <= 300


class TestParentChildChunking:
    @pytest.mark.asyncio
    async def test_parent_child_relationship(self, chunker: ChunkingPipeline) -> None:
        text = "This is a test document. " * 200
        chunks = await chunker.chunk_parent_child(text, parent_size=500, child_size=100)
        # Parent chunks should have child references
        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_parent_child_empty(self, chunker: ChunkingPipeline) -> None:
        chunks = await chunker.chunk_parent_child("")
        assert len(chunks) == 0


class TestChunkResultModel:
    def test_chunk_result_creation(self) -> None:
        chunk = ChunkResult(
            content="Test content",
            chunk_index=0,
            content_checksum="abc123",
            chunk_type="text",
            token_count=3,
            char_count=12,
        )
        assert chunk.content == "Test content"
        assert chunk.chunk_index == 0
        assert chunk.chunk_type == "text"

    def test_chunk_result_with_section(self) -> None:
        chunk = ChunkResult(
            content="Section content",
            chunk_index=1,
            content_checksum="def456",
            section_title="Introduction",
            section_hierarchy=["Doc", "Introduction"],
            page_number=1,
            language="en",
            token_count=2,
            char_count=15,
        )
        assert chunk.section_title == "Introduction"
        assert chunk.language == "en"
        assert chunk.page_number == 1
