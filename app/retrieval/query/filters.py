"""Metadata filter builder — converts high-level filter dicts to store-specific expressions.

Supports building Milvus filter expressions and BM25 metadata filters
from a common filter specification.
"""

from __future__ import annotations

from typing import Any

from app.retrieval.exceptions import FilterError


class FilterBuilder:
    """Builds filter expressions for different backends from a common spec.

    The input ``filters`` dict supports:
        - Simple field filters: ``{"language": "en", "document_id": "abc"}``
        - Range filters: ``{"page_number": {"gte": 1, "lte": 10}}``
        - List filters: ``{"source": ["pdf", "docx"]}``

    Usage:
        builder = FilterBuilder()
        milvus_expr = builder.to_milvus_expr({"language": "en"})
        bm25_filter = builder.to_bm25_fn({"document_id": "abc"})
    """

    @staticmethod
    def to_milvus_expr(filters: dict[str, Any]) -> str:
        """Convert a filters dict to a Milvus filter expression.

        Args:
            filters: Dict of field -> value filter specifications.

        Returns:
            Milvus-compatible filter expression string.

        Raises:
            FilterError: If a filter value type is unsupported.
        """
        exprs: list[str] = []

        for key, value in filters.items():
            if isinstance(value, str):
                exprs.append(f'{key} == "{value}"')
            elif isinstance(value, (int, float)):
                exprs.append(f"{key} == {value}")
            elif isinstance(value, bool):
                exprs.append(f"{key} == {str(value).lower()}")
            elif isinstance(value, list):
                if value:
                    items = ", ".join(f'"{v}"' if isinstance(v, str) else str(v) for v in value)
                    exprs.append(f"{key} in [{items}]")
            elif isinstance(value, dict):
                # Range filter: {"gte": 1, "lte": 10}
                range_exprs = []
                if "gte" in value:
                    range_exprs.append(f"{key} >= {value['gte']}")
                if "lte" in value:
                    range_exprs.append(f"{key} <= {value['lte']}")
                if "gt" in value:
                    range_exprs.append(f"{key} > {value['gt']}")
                if "lt" in value:
                    range_exprs.append(f"{key} < {value['lt']}")
                exprs.extend(range_exprs)
            elif value is not None:
                raise FilterError(f"Unsupported filter type for '{key}': {type(value).__name__}")

        return " && ".join(exprs) if exprs else ""

    @staticmethod
    def to_bm25_fn(filters: dict[str, Any]) -> Any:
        """Build a filter function for BM25 post-filtering.

        Args:
            filters: Dict of field -> value filter specifications.

        Returns:
            A callable that takes a BM25IndexEntry and returns bool.
        """
        if not filters:
            return lambda _: True

        def _filter_fn(entry: Any) -> bool:
            """Check if an entry matches all filter criteria."""
            for key, value in filters.items():
                if key == "document_id":
                    if entry.document_id != value:
                        return False
                elif key == "language":
                    if entry.language != value:
                        return False
                elif key == "metadata" and hasattr(entry, "metadata"):
                    if isinstance(value, dict):
                        for mk, mv in value.items():
                            if entry.metadata.get(mk) != mv:
                                return False
                elif key.startswith("metadata."):
                    meta_key = key[9:]
                    if hasattr(entry, "metadata"):
                        if entry.metadata.get(meta_key) != value:
                            return False
                elif hasattr(entry, key):
                    if getattr(entry, key) != value:
                        return False
            return True

        return _filter_fn

    @staticmethod
    def validate_filters(filters: dict[str, Any]) -> list[str]:
        """Validate a filters dict and return any error messages.

        Args:
            filters: Dict of field -> value filter specifications.

        Returns:
            List of validation errors (empty list = valid).
        """
        errors: list[str] = []

        for key, value in filters.items():
            if isinstance(value, dict):
                supported = {"gte", "lte", "gt", "lt"}
                unsupported = set(value.keys()) - supported
                if unsupported:
                    errors.append(f"Unsupported range operators for '{key}': {unsupported}")
            elif isinstance(value, list):
                if len(value) == 0:
                    errors.append(f"Empty list filter for '{key}'")
            elif value is None:
                errors.append(f"Null filter value for '{key}'")

        return errors
