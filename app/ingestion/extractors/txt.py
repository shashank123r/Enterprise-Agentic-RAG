"""TXT extractor — all sync calls offloaded via run_in_executor."""

from app.ingestion.executor import run_in_executor
from app.ingestion.extractors import (
    BaseExtractor, ExtractionResult, PageResult, extractor_registry,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


@extractor_registry.register("text/plain")
class TxtExtractor(BaseExtractor):
    """Extract content from plain text files."""

    async def extract(self) -> ExtractionResult:
        def _do() -> ExtractionResult:
            r = ExtractionResult()
            content = self.file_path.read_text("utf-8", errors="replace")
            r.metadata.update({"title": self.file_path.stem, "char_count": len(content), "line_count": len(content.splitlines()), "word_count": len(content.split())})
            lines = content.splitlines()
            for page_num in range(0, len(lines), 50):
                page_lines = lines[page_num:page_num + 50]
                r.pages.append(PageResult(page_number=(page_num // 50) + 1, text="\n".join(page_lines), section_title=f"Lines {page_num + 1}-{page_num + len(page_lines)}"))
            r.text = content
            return r
        return await run_in_executor(_do)

    async def extract_text(self) -> str:
        def _do() -> str:
            return self.file_path.read_text("utf-8", errors="replace")
        return await run_in_executor(_do)

    async def extract_metadata(self) -> dict:
        def _do() -> dict:
            content = self.file_path.read_text("utf-8", errors="replace")
            lines = content.splitlines()
            non_empty = [l for l in lines if l.strip()]
            return {"title": self.file_path.stem, "char_count": len(content), "line_count": len(lines), "non_empty_lines": len(non_empty), "word_count": len(content.split()), "file_size": len(content.encode("utf-8")), "encoding": "utf-8"}
        return await run_in_executor(_do)
