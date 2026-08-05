"""Tests for new enterprise chunking strategies (code-aware, OCR, pipeline)."""

from __future__ import annotations

import pytest

from app.ingestion.chunking import (
    CodeAwareChunker,
    OCRChunker,
    ParentChildChunker,
    ChunkingPipeline,
)


class TestCodeAwareChunker:
    @pytest.mark.asyncio
    async def test_python_splits_at_functions(self):
        chunker = CodeAwareChunker(max_chunk_size=2000, min_chunk_size=10)
        code = (
            "import os\n\n"
            "def func_a():\n    return 1\n\n"
            "def func_b():\n    return 2\n\n"
            "class MyClass:\n    pass\n"
        )
        chunks = await chunker.chunk(code)
        assert len(chunks) >= 1
        for c in chunks:
            assert c.chunk_type == "code"

    @pytest.mark.asyncio
    async def test_language_detection_python(self):
        chunker = CodeAwareChunker()
        assert chunker._detect_language("def foo():\n    return 1\nimport sys") == "python"

    @pytest.mark.asyncio
    async def test_language_detection_javascript(self):
        chunker = CodeAwareChunker()
        lang = chunker._detect_language("const add = (a, b) => a + b;\nfunction greet() {}")
        assert lang in ("javascript", "typescript")

    @pytest.mark.asyncio
    async def test_sql_detection(self):
        chunker = CodeAwareChunker()
        lang = chunker._detect_language(
            "SELECT id FROM users WHERE active=1;\nCREATE TABLE t (x INT);"
        )
        assert lang == "sql"


class TestOCRChunker:
    @pytest.mark.asyncio
    async def test_joins_mid_sentence_line_breaks(self):
        chunker = OCRChunker(max_chunk_size=2000, min_chunk_size=5)
        ocr_text = "This sentence was split\nacross two lines by OCR.\nNew paragraph here."
        chunks = await chunker.chunk(ocr_text)
        full = " ".join(c.content for c in chunks)
        assert "split" in full and "OCR" in full

    @pytest.mark.asyncio
    async def test_chunk_type_ocr(self):
        chunker = OCRChunker(min_chunk_size=5)
        chunks = await chunker.chunk("OCR text. Another sentence.")
        for c in chunks:
            assert c.chunk_type == "ocr_text"


class TestParentChildChunker:
    @pytest.mark.asyncio
    async def test_child_chunks_have_parent_id(self):
        chunker = ParentChildChunker(parent_chunk_size=600, child_chunk_size=200)
        text = "# Header\n" + ("Content sentence here. " * 30)
        chunks = await chunker.chunk(text)
        children = [c for c in chunks if c.chunk_type == "child"]
        assert all(c.parent_chunk_id is not None for c in children)

    @pytest.mark.asyncio
    async def test_children_inherit_section_title(self):
        chunker = ParentChildChunker(parent_chunk_size=600, child_chunk_size=200)
        text = "# My Section\n" + ("Long content. " * 30)
        chunks = await chunker.chunk(text)
        children = [c for c in chunks if c.chunk_type == "child"]
        if children:
            assert all(c.section_title is not None for c in children)


class TestChunkingPipeline:
    @pytest.mark.asyncio
    async def test_auto_code_detection(self):
        pipeline = ChunkingPipeline()
        code = "import numpy as np\ndef train():\n    pass\nclass Model:\n    pass"
        chunks = await pipeline.chunk_document(code, strategy="auto", mime_type="text/x-python")
        assert len(chunks) >= 1

    @pytest.mark.asyncio
    async def test_empty_chunks_removed(self):
        pipeline = ChunkingPipeline()
        chunks = await pipeline.chunk_document("Real content here with enough words.")
        for c in chunks:
            assert c.content.strip()

    @pytest.mark.asyncio
    async def test_chunk_indices_sequential(self):
        pipeline = ChunkingPipeline()
        text = "\n\n".join(["Paragraph " + str(i) + " content words here." for i in range(8)])
        chunks = await pipeline.chunk_document(text)
        for i, c in enumerate(chunks):
            assert c.chunk_index == i
