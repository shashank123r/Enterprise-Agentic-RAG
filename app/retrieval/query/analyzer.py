"""Query analyzer — normalizes queries, detects language, and extracts metadata.

Prepares raw user queries for retrieval by cleaning, normalizing,
and extracting any embedded metadata filters.
"""

from __future__ import annotations

import re
from typing import Any

from langdetect import detect as _detect_lang

from app.core.logging import get_logger

logger = get_logger(__name__)

# Common stopwords for filtering
_STOPWORDS: set[str] = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "by",
    "with",
    "from",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "could",
    "should",
    "may",
    "might",
    "shall",
    "can",
    "need",
    "dare",
    "ought",
    "used",
    "it",
    "its",
    "it's",
    "this",
    "that",
    "these",
    "those",
    "i",
    "me",
    "my",
    "myself",
    "we",
    "us",
    "our",
    "you",
    "your",
    "he",
    "him",
    "his",
    "she",
    "her",
    "they",
    "them",
    "their",
    "what",
    "which",
    "who",
    "whom",
    "when",
    "where",
    "why",
    "how",
    "all",
    "each",
    "every",
    "both",
    "few",
    "more",
    "most",
    "other",
    "some",
    "such",
    "no",
    "nor",
    "not",
    "only",
    "own",
    "same",
    "so",
    "than",
    "too",
    "very",
    "just",
    "because",
    "as",
    "until",
    "while",
    "about",
    "between",
    "through",
    "during",
    "before",
    "after",
    "above",
    "below",
    "up",
    "down",
    "out",
    "off",
    "over",
    "under",
    "again",
    "further",
    "then",
    "once",
}


class QueryAnalyzerResult:
    """Result of query analysis."""

    def __init__(
        self,
        normalized_query: str = "",
        language: str = "en",
        detected_stopwords: list[str] | None = None,
        has_metadata_filters: bool = False,
        metadata_filters: dict[str, Any] | None = None,
        query_type: str = "factual",
        token_count: int = 0,
        is_question: bool = False,
    ) -> None:
        self.normalized_query = normalized_query
        self.language = language
        self.detected_stopwords = detected_stopwords or []
        self.has_metadata_filters = has_metadata_filters
        self.metadata_filters = metadata_filters or {}
        self.query_type = query_type
        self.token_count = token_count
        self.is_question = is_question


class QueryAnalyzer:
    """Analyzes and normalizes queries before retrieval.

    Usage:
        analyzer = QueryAnalyzer()
        result = await analyzer.analyze("What is the revenue for Q3 2024?")
    """

    async def analyze(self, query: str) -> QueryAnalyzerResult:
        """Analyze a query: normalize, detect language, extract metadata.

        Args:
            query: Raw user query.

        Returns:
            QueryAnalyzerResult with normalized query and metadata.
        """
        normalized = self._normalize(query)
        language = await self._detect_language(normalized)
        stopwords = self._extract_stopwords(normalized)
        metadata_filters = self._extract_metadata_filters(normalized)
        token_count = len(normalized.split())
        is_question = self._is_question(normalized)
        query_type = self._classify_query_type(normalized)

        return QueryAnalyzerResult(
            normalized_query=normalized,
            language=language,
            detected_stopwords=stopwords,
            has_metadata_filters=bool(metadata_filters),
            metadata_filters=metadata_filters,
            query_type=query_type,
            token_count=token_count,
            is_question=is_question,
        )

    @staticmethod
    def _normalize(query: str) -> str:
        """Normalize a query: strip, collapse whitespace, basic cleaning.

        Args:
            query: Raw query string.

        Returns:
            Cleaned query string.
        """
        # Strip whitespace
        cleaned = query.strip()

        # Collapse multiple spaces
        cleaned = re.sub(r"\s+", " ", cleaned)

        # Remove leading/trailing punctuation
        cleaned = cleaned.strip(".,!?;:'\"()[]{}")

        return cleaned

    @staticmethod
    async def _detect_language(text: str) -> str:
        """Detect the language of a query.

        Args:
            text: Query text.

        Returns:
            ISO language code (defaults to 'en').
        """
        if len(text) < 10:
            return "en"
        try:
            return _detect_lang(text)
        except Exception:
            return "en"

    @staticmethod
    def _extract_stopwords(text: str) -> list[str]:
        """Extract stopwords from the query.

        Args:
            text: Query text.

        Returns:
            List of detected stopwords.
        """
        words = text.lower().split()
        return [w for w in words if w in _STOPWORDS]

    @staticmethod
    def _extract_metadata_filters(query: str) -> dict[str, Any]:
        """Extract embedded metadata filters from a query.

        Supports patterns like:
            "year:2024 reports"
            "language:en documentation"
            "author:Smith papers"
            "tag:finance documents"

        Args:
            query: Query text.

        Returns:
            Dict of extracted metadata filters.
        """
        filters: dict[str, Any] = {}
        pattern = r"(year|date|language|author|tag|type|section):(\S+)"
        matches = re.findall(pattern, query, re.IGNORECASE)

        for key, value in matches:
            filters[key.lower()] = value.strip(".,!?;:'\"")

        return filters

    @staticmethod
    def _is_question(text: str) -> bool:
        """Check if a query is a question.

        Args:
            text: Query text.

        Returns:
            True if the query appears to be a question.
        """
        question_starters = [
            "what",
            "why",
            "when",
            "where",
            "how",
            "who",
            "which",
            "whose",
            "whom",
            "can",
            "could",
            "would",
            "should",
            "is",
            "are",
            "was",
            "were",
            "do",
            "does",
            "did",
            "has",
            "have",
            "had",
            "tell me",
            "explain",
            "describe",
        ]
        return any(text.lower().startswith(s) for s in question_starters) or text.endswith("?")

    @staticmethod
    def _classify_query_type(text: str) -> str:
        """Classify the query type.

        Args:
            text: Query text.

        Returns:
            Query type: 'factual', 'explanatory', 'comparative', 'procedural', 'exploratory'.
        """
        lower = text.lower()

        comparative = {"vs", "versus", "compare", "difference", "better", "worse", "vs."}
        procedural = {"how to", "steps", "procedure", "guide", "tutorial", "instructions"}
        explanatory = {"explain", "why", "describe", "what is", "how does", "meaning"}
        exploratory = {"tell me about", "information", "overview", "summary", "background"}

        words = set(lower.split())

        if words & comparative:
            return "comparative"
        if any(lower.startswith(p) for p in procedural):
            return "procedural"
        if any(lower.startswith(p) for p in explanatory) and not words & comparative:
            return "explanatory"
        if any(lower.startswith(p) for p in exploratory):
            return "exploratory"

        return "factual"
