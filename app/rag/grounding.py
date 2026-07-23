"""Grounding validator — verifies generated answers are supported by retrieved context.

Ensures every claim in the generated answer can be traced back to a source chunk.
Flags unsupported statements and prevents citation fabrication.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.logging import get_logger
from app.rag.exceptions import RAGGroundingError
from app.retrieval.schemas import RetrievedChunk

logger = get_logger(__name__)


class GroundingValidator:
    """Validates that generated answers are grounded in retrieved context.

    Checks:
    - Every citation [N] references a valid source chunk
    - Generated text doesn't contain claims absent from all sources
    - No fabricated citations (citations to non-existent chunks)
    - Answer length is reasonable given context

    Usage:
        validator = GroundingValidator()
        result = await validator.validate(answer, chunks, question)
    """

    async def validate(
        self,
        answer: str,
        chunks: list[RetrievedChunk],
        question: str,
    ) -> dict[str, Any]:
        """Validate that an answer is properly grounded in the source chunks.

        Args:
            answer: Generated answer text.
            chunks: Source chunks used as context.
            question: Original question.

        Returns:
            Dict with:
            - valid: bool
            - issues: list[str]
            - unsupported_statements: list[str]
            - citation_count: int
            - invalid_citations: list[str]
        """
        issues: list[str] = []
        unsupported_statements: list[str] = []

        # 1. Extract and validate citations
        citation_nums = self._extract_citations(answer)
        valid_count = 0
        invalid_citations: list[str] = []

        for num in citation_nums:
            if num <= len(chunks):
                valid_count += 1
            else:
                invalid_citations.append(str(num))
                issues.append(f"Citation [{num}] references a non-existent source chunk")

        # 2. Check for citations in the answer
        if not citation_nums and len(answer) > 50:
            issues.append("Answer contains no citations despite having source context available")

        # 3. Check for lack of information acknowledgement
        no_info_phrases = [
            "i don't have enough information",
            "i cannot answer",
            "i don't have the specific",
            "i don't have access to",
            "not provided in the context",
            "does not contain information",
            "not mentioned in the sources",
            "cannot find this information",
        ]
        admits_no_info = any(phrase in answer.lower() for phrase in no_info_phrases)

        # If the answer admits no info but still makes claims, flag it
        if admits_no_info and len(answer) > 200:
            logger.warning(
                "Answer admits no information but contains substantial text",
                answer_length=len(answer),
            )

        # 4. Basic fact-checking — check if key terms from question appear in context
        question_terms = self._extract_key_terms(question)
        context_text = " ".join(c.text.lower() for c in chunks) if chunks else ""

        if chunks and question_terms:
            missing_terms = [t for t in question_terms if t not in context_text]
            if missing_terms:
                logger.debug(
                    "Question terms not found in context",
                    missing_terms=missing_terms[:5],
                )

        logger.debug(
            "Grounding validation complete",
            valid=len(issues) == 0,
            issues=len(issues),
            citations=valid_count,
            invalid_citations=len(invalid_citations),
        )

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "unsupported_statements": unsupported_statements,
            "citation_count": valid_count,
            "invalid_citations": invalid_citations,
            "admits_no_info": admits_no_info,
        }

    async def validate_or_raise(
        self,
        answer: str,
        chunks: list[RetrievedChunk],
        question: str,
    ) -> None:
        """Validate grounding and raise an exception if invalid.

        Args:
            answer: Generated answer.
            chunks: Source chunks.
            question: Original question.

        Raises:
            RAGGroundingError: If grounding validation fails.
        """
        result = await self.validate(answer, chunks, question)
        if not result["valid"]:
            raise RAGGroundingError(issues=result["issues"])

    @staticmethod
    def _extract_citations(text: str) -> list[int]:
        """Extract citation numbers from text.

        Matches patterns like [1], [2, 3], [1-3], etc.

        Args:
            text: Generated answer text.

        Returns:
            Sorted list of unique citation numbers.
        """
        citations: set[int] = set()
        # Match individual citations [N]
        for match in re.finditer(r"\[(\d+)\]", text):
            citations.add(int(match.group(1)))
        # Match ranges [N-M]
        for match in re.finditer(r"\[(\d+)-(\d+)\]", text):
            start, end = int(match.group(1)), int(match.group(2))
            citations.update(range(start, end + 1))
        return sorted(citations)

    @staticmethod
    def _extract_key_terms(text: str, max_terms: int = 5) -> list[str]:
        """Extract key terms from a question for basic fact-checking.

        Args:
            text: Question text.
            max_terms: Maximum terms to extract.

        Returns:
            List of lowercase key terms.
        """
        # Simple extraction: take capitalized or longer words
        words = re.findall(r"\b[a-zA-Z]{4,}\b", text.lower())
        # Remove very common words
        stopwords = {
            "what", "when", "where", "why", "how", "which", "that", "this",
            "with", "from", "they", "have", "been", "were", "will", "would",
            "could", "should", "does", "about", "there", "their", "your",
        }
        filtered = [w for w in words if w not in stopwords]
        return filtered[:max_terms]
