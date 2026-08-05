"""Tests for the semantic grounding validator."""

from __future__ import annotations

import pytest

from app.rag.grounding import GroundingValidator, _cosine_similarity, _tfidf_vector, _build_idf
from app.retrieval.schemas import RetrievedChunk


def _make_chunk(chunk_id: str, text: str, score: float = 0.9) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id="doc1",
        text=text,
        score=score,
    )


class TestGroundingValidator:
    @pytest.mark.asyncio
    async def test_valid_with_citation_and_supported_text(self):
        validator = GroundingValidator()
        chunks = [_make_chunk("c1", "Machine learning models require large datasets and compute.")]
        answer = "Machine learning requires large datasets and computational resources. [1]"
        result = await validator.validate(answer, chunks, "What does ML require?")
        assert result["valid"] is True
        assert result["citation_count"] == 1

    @pytest.mark.asyncio
    async def test_invalid_citation_out_of_range(self):
        validator = GroundingValidator()
        chunks = [_make_chunk("c1", "Some content.")]
        answer = "Reference to source [5] which does not exist."
        result = await validator.validate(answer, chunks, "Q?")
        assert not result["valid"]
        assert "5" in result["invalid_citations"]

    @pytest.mark.asyncio
    async def test_missing_citation_for_long_answer(self):
        validator = GroundingValidator()
        chunks = [_make_chunk("c1", "Revenue grew significantly.")]
        # Long answer with no citation
        answer = "The revenue grew significantly and the company expanded into new markets last year."
        result = await validator.validate(answer, chunks, "How did revenue change?")
        # Should flag missing citations
        assert any("citation" in issue.lower() for issue in result["issues"])

    @pytest.mark.asyncio
    async def test_no_chunks_skips_semantic_validation(self):
        validator = GroundingValidator()
        result = await validator.validate("Some answer text.", [], "Q?")
        assert "confidence" in result
        assert result["confidence"] == 1.0

    @pytest.mark.asyncio
    async def test_admits_no_info_detected(self):
        validator = GroundingValidator()
        chunks = [_make_chunk("c1", "Company sells software.")]
        answer = "I don't have enough information to answer this question."
        result = await validator.validate(answer, chunks, "Q?")
        assert result["admits_no_info"] is True

    @pytest.mark.asyncio
    async def test_confidence_is_in_range(self):
        validator = GroundingValidator()
        chunks = [_make_chunk("c1", "Neural networks learn from data.")]
        answer = "Neural networks are trained on data. [1]"
        result = await validator.validate(answer, chunks, "Q?")
        assert 0.0 <= result["confidence"] <= 1.0

    @pytest.mark.asyncio
    async def test_sentence_scores_populated(self):
        validator = GroundingValidator()
        chunks = [_make_chunk("c1", "Revenue grew by 23 percent year over year.")]
        answer = "Revenue grew 23 percent year over year. [1]"
        result = await validator.validate(answer, chunks, "Q?")
        assert isinstance(result["sentence_scores"], list)

    @pytest.mark.asyncio
    async def test_extract_citations_range(self):
        from app.rag.grounding import GroundingValidator
        v = GroundingValidator()
        assert v._extract_citations("See [1-3] and [5].") == [1, 2, 3, 5]

    @pytest.mark.asyncio
    async def test_extract_citations_individual(self):
        from app.rag.grounding import GroundingValidator
        v = GroundingValidator()
        assert v._extract_citations("See [1] and [2].") == [1, 2]


class TestTFIDFHelpers:
    def test_cosine_similarity_identical(self):
        idf = {"word": 1.0, "test": 1.0}
        a = _tfidf_vector("word test", idf)
        b = _tfidf_vector("word test", idf)
        assert _cosine_similarity(a, b) == pytest.approx(1.0)

    def test_cosine_similarity_orthogonal(self):
        idf = {"apple": 1.0, "banana": 1.0, "car": 1.0, "dog": 1.0}
        a = _tfidf_vector("apple banana", idf)
        b = _tfidf_vector("car dog", idf)
        assert _cosine_similarity(a, b) == pytest.approx(0.0)

    def test_cosine_similarity_empty(self):
        assert _cosine_similarity({}, {"word": 1.0}) == 0.0

    def test_build_idf_penalizes_common_terms(self):
        docs = ["word word common", "word common unique", "another text here"]
        idf = _build_idf(docs)
        # "word" appears in 2 docs, "unique" in 1 → unique should have higher IDF
        assert idf.get("unique", 0) >= idf.get("word", 0)
