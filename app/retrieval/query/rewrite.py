"""Query rewriter — reformulates queries for better retrieval.

Supports rule-based rewriting (no LLM dependency required).
More sophisticated LLM-based rewriting can be added later.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.logging import get_logger
from app.retrieval.exceptions import QueryError

logger = get_logger(__name__)


class QueryRewriter:
    """Rewrites queries to improve retrieval quality.

    Uses rule-based transformations:
    - Expands contractions
    - Removes redundant question prefixes
    - Converts questions to declarative form
    - Adds missing context markers

    Usage:
        rewriter = QueryRewriter()
        rewritten = await rewriter.rewrite("What is the revenue?")
    """

    async def rewrite(
        self,
        query: str,
        language: str = "en",
        **kwargs: Any,
    ) -> str:
        """Rewrite a query for improved retrieval.

        Args:
            query: Original query string.
            language: ISO language code (default 'en').
            **kwargs: Additional parameters.

        Returns:
            Rewritten query string.

        Raises:
            QueryError: If rewriting fails.
        """
        try:
            rewritten = query.strip()

            # Step 1: Expand contractions
            rewritten = self._expand_contractions(rewritten)

            # Step 2: Remove leading question prefixes
            rewritten = self._remove_question_prefix(rewritten)

            # Step 3: Convert questions to declarative form
            rewritten = self._question_to_declarative(rewritten)

            # Step 4: Add retrieval context marker
            rewritten = self._add_context_marker(rewritten, language)

            if rewritten != query:
                logger.debug(
                    "Query rewritten",
                    original=query[:80],
                    rewritten=rewritten[:80],
                )

            return rewritten

        except Exception as e:
            raise QueryError(f"Query rewriting failed: {e}")

    @staticmethod
    def _expand_contractions(text: str) -> str:
        """Expand common English contractions.

        Args:
            text: Input text.

        Returns:
            Text with contractions expanded.
        """
        contractions = {
            r"\bdon't\b": "do not",
            r"\bdoesn't\b": "does not",
            r"\bdidn't\b": "did not",
            r"\bwon't\b": "will not",
            r"\bwouldn't\b": "would not",
            r"\bcouldn't\b": "could not",
            r"\bshouldn't\b": "should not",
            r"\bcan't\b": "cannot",
            r"\bcannot\b": "can not",
            r"\bhaven't\b": "have not",
            r"\bhasn't\b": "has not",
            r"\bhadn't\b": "had not",
            r"\bwasn't\b": "was not",
            r"\bweren't\b": "were not",
            r"\bain't\b": "is not",
            r"\bit's\b": "it is",
            r"\bthat's\b": "that is",
            r"\bwhat's\b": "what is",
            r"\bwho's\b": "who is",
            r"\bwhere's\b": "where is",
            r"\bwhy's\b": "why is",
            r"\bhow's\b": "how is",
            r"\bhere's\b": "here is",
            r"\bthere's\b": "there is",
            r"\bhe's\b": "he is",
            r"\bshe's\b": "she is",
            r"\bit'll\b": "it will",
            r"\bthat'll\b": "that will",
            r"\bwe'll\b": "we will",
            r"\byou'll\b": "you will",
            r"\bthey'll\b": "they will",
            r"\bthey're\b": "they are",
            r"\bwe're\b": "we are",
            r"\byou're\b": "you are",
        }
        for pattern, replacement in contractions.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text

    @staticmethod
    def _remove_question_prefix(text: str) -> str:
        """Remove leading question prefixes for better keyword matching.

        Example:
            "What is the revenue for Q3?" → "revenue for Q3"
            "Tell me about machine learning" → "machine learning"

        Args:
            text: Input text.

        Returns:
            Text with question prefix removed.
        """
        prefixes = [
            r"^(can you|could you|would you|will you)\s+(tell me|show me|list|give me|provide)\s+(about|the|me|)\s+",
            r"^(i want to know|i need to know|i'd like to know)\s+",
            r"^(tell me|show me|list|give me|find me)\s+(about|the|all|)\s+",
            r"^(what is|what are|what was|what were)\s+(a|an|the|)\s+",
            r"^(what does|what do|what did)\s+(a|an|the|)\s+",
            r"^(how (do|does|did|can|would|could) (i|you|we) )\s+",
            r"^(why (do|does|did|would) )\s+",
        ]
        for prefix in prefixes:
            match = re.match(prefix, text, re.IGNORECASE)
            if match:
                return text[match.end():].strip()
        return text

    @staticmethod
    def _question_to_declarative(text: str) -> str:
        """Convert a question to declarative form.

        Example:
            "What is machine learning?" → "machine learning definition"

        Args:
            text: Input text.

        Returns:
            Text in declarative form with context words added.
        """
        lower = text.lower().strip("?.")

        # Add context words for better BM25 matching
        if lower.startswith("what is ") or lower.startswith("what are "):
            subject = re.sub(r"^(what is |what are )(a |an |the |)", "", lower)
            return f"{subject} what is definition"
        if lower.startswith("what does ") or lower.startswith("what do "):
            subject = re.sub(r"^(what does |what do )(a |an |the |)", "", lower)
            return f"{subject} what does"
        if lower.startswith("how to "):
            return lower
        if lower.startswith("why "):
            subject = lower[4:]
            return f"{subject} reasons why"
        if lower.startswith("when "):
            subject = lower[5:]
            return f"{subject} date timeline"

        return text

    @staticmethod
    def _add_context_marker(text: str, language: str) -> str:
        """Add language context marker for multilingual indexes.

        Args:
            text: Query text.
            language: Detected language code.

        Returns:
            Text with optional language marker.
        """
        # For now, just return the text as-is.
        # In a multilingual setup, you could prefix with language info.
        return text
