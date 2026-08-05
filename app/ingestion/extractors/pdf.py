"""PDF document extractor — text, tables, images, and OCR.

All synchronous library calls wrapped with ``run_in_executor``.
"""

import re
from pathlib import Path

from app.core.logging import get_logger
from app.ingestion.executor import run_in_executor
from app.ingestion.extractors import (
    BaseExtractor,
    ExtractionResult,
    ImageResult,
    PageResult,
    TableResult,
    extractor_registry,
)

logger = get_logger(__name__)


@extractor_registry.register("application/pdf")
class PdfExtractor(BaseExtractor):
    """Extract text, tables, images, and metadata from PDF documents."""

    async def extract(self) -> ExtractionResult:
        result = ExtractionResult()
        await self._extract_metadata(result)
        await self._extract_text_and_tables(result)
        await self._extract_images(result)
        result.text = "\n\n".join(p.text for p in result.pages if p.text.strip())
        return result

    async def extract_text(self) -> str:
        result = ExtractionResult()
        await self._extract_text_and_tables(result)
        return "\n\n".join(p.text for p in result.pages if p.text.strip())

    async def extract_metadata(self) -> dict:
        try:
            from pypdf import PdfReader

            def _read_metadata() -> dict:
                reader = PdfReader(str(self.file_path))
                info = reader.metadata or {}
                meta = {
                    "title": info.get("/Title", ""),
                    "author": info.get("/Author", ""),
                    "subject": info.get("/Subject", ""),
                    "creator": info.get("/Creator", ""),
                    "producer": info.get("/Producer", ""),
                    "page_count": len(reader.pages),
                    "pdf_version": reader.pdf_header,
                }
                raw_created = info.get("/CreationDate", "")
                raw_modified = info.get("/ModDate", "")
                if raw_created:
                    meta["creation_date"] = self._parse_pdf_date(raw_created)
                if raw_modified:
                    meta["modified_date"] = self._parse_pdf_date(raw_modified)
                keywords = info.get("/Keywords", "")
                if keywords:
                    meta["keywords"] = [k.strip() for k in keywords.split(",") if k.strip()]
                return meta

            return await run_in_executor(_read_metadata)
        except Exception as e:
            logger.warning("Failed to extract PDF metadata", exc_info=e)
            return {}

    async def detect_needs_ocr(self) -> bool:
        try:
            from pypdf import PdfReader

            def _check_text_pages() -> bool:
                reader = PdfReader(str(self.file_path))
                text_pages = sum(1 for p in reader.pages if (p.extract_text() or "").strip())
                total = len(reader.pages)
                return total > 0 and (text_pages / total) < 0.2

            return await run_in_executor(_check_text_pages)
        except Exception:
            return False

    async def _extract_metadata(self, result: ExtractionResult) -> None:
        meta = await self.extract_metadata()
        result.metadata.update(meta)

    async def _extract_text_and_tables(self, result: ExtractionResult) -> None:
        try:
            import pdfplumber

            def _extract_with_pdfplumber() -> None:
                with pdfplumber.open(str(self.file_path)) as pdf:
                    for page_num, page in enumerate(pdf.pages, start=1):
                        page_text = page.extract_text() or ""
                        section_title = self._detect_section_title(page_text)
                        result.pages.append(
                            PageResult(
                                page_number=page_num, text=page_text, section_title=section_title
                            )
                        )
                        tables = page.extract_tables() or []
                        for t_idx, t_data in enumerate(tables):
                            if not t_data:
                                continue
                            headers = [h or "" for h in (t_data[0] if t_data else [])]
                            rows = [
                                [c or "" for c in row]
                                for row in (t_data[1:] if len(t_data) > 1 else [])
                            ]
                            result.tables.append(
                                TableResult(
                                    page_number=page_num,
                                    table_index=t_idx,
                                    headers=headers,
                                    rows=rows,
                                )
                            )

            await run_in_executor(_extract_with_pdfplumber)
        except Exception as e:
            logger.warning("pdfplumber failed, falling back to pypdf", exc_info=e)
            await self._fallback_text_extraction(result)

    async def _fallback_text_extraction(self, result: ExtractionResult) -> None:
        try:
            from pypdf import PdfReader

            def _extract_pypdf() -> None:
                reader = PdfReader(str(self.file_path))
                for page_num, page in enumerate(reader.pages, start=1):
                    text = page.extract_text() or ""
                    result.pages.append(PageResult(page_number=page_num, text=text))

            await run_in_executor(_extract_pypdf)
        except Exception as e:
            result.add_error(f"PDF text extraction failed: {e}")

    async def _extract_images(self, result: ExtractionResult) -> None:
        try:
            from pypdf import PdfReader

            def _extract() -> None:
                reader = PdfReader(str(self.file_path))
                image_count = 0
                for page_num, page in enumerate(reader.pages, start=1):
                    for img in page.images:
                        image_count += 1
                        fmt = Path(img.name).suffix.lstrip(".").lower() or "png"
                        result.images.append(
                            ImageResult(
                                page_number=page_num,
                                image_index=image_count,
                                image_data=img.data,
                                format=fmt,
                                caption=f"Image from page {page_num}",
                            )
                        )

            await run_in_executor(_extract)
        except Exception as e:
            logger.warning("Failed to extract PDF images", exc_info=e)

    @staticmethod
    def _detect_section_title(text: str) -> str | None:
        lines = text.strip().split("\n")
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if (
                len(stripped) < 100
                and not stripped.endswith(".")
                and re.search(r"^[A-Z][a-z]", stripped)
            ):
                return stripped
        return None

    @staticmethod
    def _parse_pdf_date(date_str: str) -> str | None:
        m = re.match(r"D:(\d{4})(\d{2})(\d{2})", date_str)
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None
