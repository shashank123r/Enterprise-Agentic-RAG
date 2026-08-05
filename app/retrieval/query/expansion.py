"""Query expansion — expands queries with synonyms and related terms.

Improves recall by adding contextually relevant terms to the query.
Uses a built-in synonym dictionary (no external API required).
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.retrieval.exceptions import QueryError

logger = get_logger(__name__)

# Built-in synonym dictionary for common technical/business terms
_SYNONYMS: dict[str, list[str]] = {
    # Business
    "revenue": ["income", "earnings", "sales", "turnover", "profit"],
    "cost": ["expense", "spend", "price", "fee", "charge"],
    "profit": ["gain", "return", "earnings", "margin"],
    "customer": ["client", "user", "consumer", "buyer"],
    "employee": ["staff", "worker", "team member", "personnel"],
    "company": ["firm", "organization", "enterprise", "corporation", "business"],
    "product": ["item", "offering", "solution", "service"],
    "market": ["marketplace", "sector", "industry", "segment"],
    "growth": ["increase", "expansion", "rise", "improvement"],
    "strategy": ["plan", "approach", "methodology", "framework"],
    "performance": ["results", "outcomes", "metrics", "efficiency"],
    "risk": ["threat", "exposure", "vulnerability", "danger"],
    "data": ["information", "dataset", "records", "statistics"],
    "analysis": ["analytics", "examination", "study", "assessment", "evaluation"],
    "report": ["document", "summary", "overview", "briefing"],
    # Technology
    "software": ["application", "program", "system", "tool"],
    "database": ["repository", "data store", "storage", "warehouse"],
    "network": ["infrastructure", "connectivity", "system"],
    "security": ["protection", "safety", "defense", "cybersecurity"],
    "api": ["interface", "endpoint", "service", "rest api"],
    "cloud": ["aws", "azure", "gcp", "hosted", "saas"],
    "algorithm": ["method", "procedure", "technique", "logic"],
    "model": ["framework", "architecture", "approach", "system"],
    "performance": ["speed", "throughput", "latency", "efficiency"],
    "scalability": ["elasticity", "capacity", "growth", "expansion"],
    # AI/ML
    "machine learning": ["ml", "deep learning", "artificial intelligence", "neural network"],
    "ai": ["artificial intelligence", "machine learning", "intelligent system"],
    "neural": ["deep learning", "network", "transformer", "model"],
    "training": ["learning", "fine-tuning", "optimization", "fitting"],
    "inference": ["prediction", "evaluation", "forward pass", "deployment"],
    "embedding": ["vector", "representation", "encoding", "feature"],
    "retrieval": ["search", "lookup", "indexing", "query"],
    "generation": ["synthesis", "creation", "production", "output"],
    # Document
    "document": ["file", "paper", "report", "article", "page"],
    "chapter": ["section", "part", "segment", "topic"],
    "figure": ["chart", "graph", "diagram", "illustration", "image"],
    "table": ["chart", "spreadsheet", "matrix", "grid"],
    "reference": ["source", "citation", "bibliography", "footnote"],
}


class QueryExpander:
    """Expands queries with synonyms and related terms.

    Uses a built-in synonym dictionary for domain-specific terms.
    Additional synonym sources can be added later.

    Usage:
        expander = QueryExpander()
        expanded = await expander.expand("machine learning revenue")
    """

    def __init__(self, max_expansions_per_term: int = 3) -> None:
        self._max_expansions = max_expansions_per_term

    async def expand(
        self,
        query: str,
        max_terms: int = 5,
        **kwargs: Any,
    ) -> str:
        """Expand a query with synonyms for key terms.

        Args:
            query: Original query text.
            max_terms: Maximum number of terms to expand.
            **kwargs: Additional parameters.

        Returns:
            Expanded query string with OR-synonyms appended.

        Raises:
            QueryError: If expansion fails.
        """
        try:
            words = query.lower().split()
            expanded_terms: list[str] = []
            expanded_count = 0

            for word in words:
                if expanded_count >= max_terms:
                    break

                # Check for multi-word synonyms first
                for phrase, synonyms in _SYNONYMS.items():
                    if phrase in query.lower():
                        if expanded_count >= max_terms:
                            break
                        # Add top synonyms
                        relevant = [
                            s
                            for s in synonyms
                            if s not in query.lower() and s not in expanded_terms
                        ]
                        expanded_terms.extend(relevant[: self._max_expansions])
                        expanded_count += 1

                # Check single word
                if word in _SYNONYMS and expanded_count < max_terms:
                    synonyms = _SYNONYMS[word]
                    relevant = [s for s in synonyms if s not in words and s not in expanded_terms]
                    expanded_terms.extend(relevant[: self._max_expansions])
                    expanded_count += 1

            if expanded_terms:
                expanded_query = f"{query} ({' '.join(expanded_terms)})"
                logger.debug(
                    "Query expanded",
                    original=query[:60],
                    expanded=expanded_query[:80],
                    added_terms=expanded_terms,
                )
                return expanded_query

            return query

        except Exception as e:
            raise QueryError(f"Query expansion failed: {e}")
