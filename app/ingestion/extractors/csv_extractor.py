"""CSV file extractor — sync calls offloaded via run_in_executor."""

import csv
import io

from app.core.logging import get_logger
from app.ingestion.executor import run_in_executor
from app.ingestion.extractors import (
    BaseExtractor,
    ExtractionResult,
    PageResult,
    TableResult,
    extractor_registry,
)

logger = get_logger(__name__)


@extractor_registry.register("text/csv")
class CsvExtractor(BaseExtractor):
    """Extract data from CSV files."""

    async def extract(self) -> ExtractionResult:
        async def _do() -> ExtractionResult:
            content = self.file_path.read_bytes()
            text = content.decode("utf-8", errors="replace")
            r = ExtractionResult()
            r.metadata.update({"title": self.file_path.stem, "file_size": len(content)})
            reader = csv.reader(io.StringIO(text))
            rows = list(reader)
            if rows:
                headers = rows[0]
                data_rows = rows[1:] if len(rows) > 1 else []
                r.metadata.update({"row_count": len(rows), "column_count": len(headers)})
                preview = (
                    f"CSV: {self.file_path.name}\nColumns: {', '.join(headers)}\nRows: {len(data_rows)}\n\n"
                    + "\n".join(" | ".join(row) for row in data_rows[:20])
                )
                r.pages.append(
                    PageResult(
                        page_number=1, text=preview, section_title=f"CSV - {len(data_rows)} rows"
                    )
                )
                r.tables.append(
                    TableResult(
                        page_number=1,
                        table_index=0,
                        headers=headers,
                        rows=data_rows,
                        caption=f"CSV: {self.file_path.name}",
                    )
                )
            r.text = text
            return r

        return await run_in_executor(_do)

    async def extract_text(self) -> str:
        async def _do() -> str:
            content = self.file_path.read_bytes()
            return content.decode("utf-8", errors="replace")

        return await run_in_executor(_do)

    async def extract_metadata(self) -> dict:
        async def _do() -> dict:
            content = self.file_path.read_bytes()
            text = content.decode("utf-8", errors="replace")
            reader = csv.reader(io.StringIO(text))
            rows = list(reader)
            return {
                "title": self.file_path.stem,
                "row_count": len(rows),
                "column_count": len(rows[0]) if rows else 0,
                "has_header": True,
                "file_size": len(content),
            }

        return await run_in_executor(_do)
