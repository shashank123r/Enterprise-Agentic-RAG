"""Base extractor class — all format extractors extend this.

Every synchronous I/O operation uses ``run_in_executor`` so the
asyncio event loop is never blocked during document processing.
"""

from abc import ABC, abstractmethod
from pathlib import Path

from app.ingestion.executor import run_in_executor
from app.ingestion.extractors import ExtractionResult


class BaseExtractor(ABC):
    """Abstract base for all document format extractors.

    All synchronous operations (file I/O, library calls) must be wrapped
    with ``await run_in_executor(...)`` to avoid blocking the event loop.
    """

    def __init__(self, file_path: str | Path) -> None:
        self.file_path = Path(file_path)

    @abstractmethod
    async def extract(self) -> ExtractionResult:
        """Extract all content from the document.

        Implementations MUST use ``await run_in_executor()`` for all
        synchronous I/O and CPU-bound operations.
        """
        ...

    @abstractmethod
    async def extract_text(self) -> str:
        """Extract only the plain text content."""
        ...

    @abstractmethod
    async def extract_metadata(self) -> dict:
        """Extract document metadata (title, author, dates, etc.)."""
        ...

    async def detect_needs_ocr(self) -> bool:
        """Check if the document contains images instead of text."""
        return False
