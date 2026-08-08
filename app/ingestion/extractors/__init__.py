"""Extractor registry — plugin-based architecture for adding new formats.

Each document format registers itself with the registry via the
``@extractor_registry.register`` decorator. The pipeline discovers
the correct extractor by MIME type.
"""

from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


class ExtractorRegistry:
    """Registry mapping MIME types to Extractor classes.

    Register a new extractor::

        @extractor_registry.register(
            "application/pdf", "application/x-pdf"
        )
        class PdfExtractor(BaseExtractor):
            ...
    """

    def __init__(self) -> None:
        self._registry: dict[str, type[BaseExtractor]] = {}

    def register(self, *mime_types: str):
        """Decorator to register an extractor for one or more MIME types."""

        def wrapper(cls: type["BaseExtractor"]) -> type["BaseExtractor"]:
            for mime in mime_types:
                self._registry[mime] = cls
                logger.debug(
                    "Registered extractor",
                    mime_type=mime,
                    extractor=cls.__name__,
                )
            return cls

        return wrapper

    def get_extractor(self, mime_type: str) -> type["BaseExtractor"] | None:
        """Get the extractor class for a given MIME type."""
        return self._registry.get(mime_type)

    @property
    def supported_mime_types(self) -> list[str]:
        """List all registered MIME types."""
        return list(self._registry.keys())

    @property
    def extractors(self) -> dict[str, type["BaseExtractor"]]:
        """Get the full registry dict."""
        return dict(self._registry)


extractor_registry = ExtractorRegistry()


class ExtractionResult:
    """Result of a document extraction containing all discovered content."""

    def __init__(self) -> None:
        self.text: str = ""
        self.pages: list[PageResult] = []
        self.tables: list[TableResult] = []
        self.images: list[ImageResult] = []
        self.metadata: dict[str, Any] = {}
        self.errors: list[str] = []

    def add_error(self, error: str) -> None:
        """Record a non-fatal extraction error."""
        self.errors.append(error)


class PageResult:
    """Content extracted from a single page."""

    def __init__(
        self,
        page_number: int,
        text: str,
        section_title: str | None = None,
    ) -> None:
        self.page_number = page_number
        self.text = text
        self.section_title = section_title


class TableResult:
    """Table extracted from a document."""

    def __init__(
        self,
        page_number: int | None,
        table_index: int,
        headers: list[str],
        rows: list[list[str]],
        caption: str | None = None,
    ) -> None:
        self.page_number = page_number
        self.table_index = table_index
        self.headers = headers
        self.rows = rows
        self.caption = caption

    def to_csv(self) -> str:
        """Convert the table to CSV format."""
        import csv
        import io

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(self.headers)
        writer.writerows(self.rows)
        return output.getvalue()

    def to_html(self) -> str:
        """Convert the table to HTML format."""
        parts = ["<table><thead><tr>"]
        for h in self.headers:
            parts.append(f"<th>{_escape_html(h)}</th>")
        parts.append("</tr></thead><tbody>")
        for row in self.rows:
            parts.append("<tr>")
            for cell in row:
                parts.append(f"<td>{_escape_html(cell)}</td>")
            parts.append("</tr>")
        parts.append("</tbody></table>")
        return "".join(parts)

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def column_count(self) -> int:
        return len(self.headers)


class ImageResult:
    """Image extracted from a document."""

    def __init__(
        self,
        page_number: int | None,
        image_index: int,
        image_data: bytes,
        format: str = "png",
        caption: str | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> None:
        self.page_number = page_number
        self.image_index = image_index
        self.image_data = image_data
        self.format = format
        self.caption = caption
        self.width = width
        self.height = height

    @property
    def size_bytes(self) -> int:
        return len(self.image_data)

    @property
    def alt_text(self) -> str:
        return self.caption or f"Image {self.image_index} on page {self.page_number}"


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


from app.ingestion.extractors.base import BaseExtractor

# Import all extractors to trigger registration
from app.ingestion.extractors import (
    csv_extractor,
    docx,
    html_extractor,
    json_extractor,
    pdf,
    pptx,
    txt,
    xlsx,
)
from app.ingestion.extractors import (
    markdown as markdown_extractor,
)

__all__ = [
    "BaseExtractor",
    "ExtractionResult",
    "ExtractorRegistry",
    "ImageResult",
    "PageResult",
    "TableResult",
    "extractor_registry",
]
