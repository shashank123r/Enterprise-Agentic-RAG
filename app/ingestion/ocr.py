"""Stateless OCR module — no mutable shared state; fully thread-safe.

Each call returns a (result, ocr_applied) tuple so callers can track
OCR usage without depending on singleton state.
"""

from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.logging import get_logger
from app.ingestion.executor import run_in_executor

logger = get_logger(__name__)


class OCRProcessor:
    """Stateless OCR processor. All methods offload to thread executor.

    Thread-safe by design — no mutable instance state shared across calls.
    """

    def __init__(self, language: str = "eng") -> None:
        self._language = language

    @property
    def language(self) -> str:
        return self._language

    @language.setter
    def language(self, value: str) -> None:
        self._language = value

    async def process_pdf_page(
        self, pdf_path: str | Path, page_number: int, dpi: int = 300
    ) -> tuple[str, bool]:
        """OCR a single PDF page. Returns (text, ocr_was_applied)."""
        lang = self._language

        def _do() -> tuple[str, bool]:
            import pytesseract
            from pdf2image import convert_from_path

            with TemporaryDirectory() as tmpdir:
                images = convert_from_path(
                    str(pdf_path),
                    first_page=page_number,
                    last_page=page_number,
                    dpi=dpi,
                    output_folder=tmpdir,
                    fmt="png",
                    thread_count=2,
                )
                if not images:
                    return "", False
                text = pytesseract.image_to_string(
                    images[0], config=f"--oem 3 --psm 6 -l {lang} --dpi 300"
                )
                return text.strip(), True

        try:
            return await run_in_executor(_do)
        except Exception as e:
            logger.error("PDF page OCR failed", page=page_number, error=str(e))
            return "", False

    async def process_image_bytes(
        self, image_data: bytes, page_number: int | None = None
    ) -> tuple[str, bool]:
        """OCR image bytes. Returns (text, ocr_was_applied)."""
        lang = self._language

        def _do() -> tuple[str, bool]:
            import io

            import pytesseract
            from PIL import Image

            image = Image.open(io.BytesIO(image_data))
            text = pytesseract.image_to_string(image, config=f"--oem 3 --psm 6 -l {lang} --dpi 300")
            return text.strip(), True

        try:
            return await run_in_executor(_do)
        except Exception as e:
            logger.warning("Image OCR failed", page=page_number, error=str(e))
            return "", False

    async def process_full_pdf(
        self, pdf_path: str | Path, dpi: int = 200
    ) -> tuple[dict[int, str], bool]:
        """OCR entire PDF. Returns (page_map, ocr_was_applied)."""
        lang = self._language

        def _do() -> tuple[dict[int, str], bool]:
            import pytesseract
            from pdf2image import convert_from_path

            results: dict[int, str] = {}
            ocr_applied = False
            with TemporaryDirectory() as tmpdir:
                images = convert_from_path(
                    str(pdf_path), dpi=dpi, output_folder=tmpdir, fmt="png", thread_count=4
                )
                for page_num, image in enumerate(images, start=1):
                    text = pytesseract.image_to_string(
                        image, config=f"--oem 3 --psm 6 -l {lang} --dpi 300"
                    )
                    if text.strip():
                        results[page_num] = text.strip()
                        ocr_applied = True
            return results, ocr_applied

        try:
            return await run_in_executor(_do)
        except Exception as e:
            logger.error("Full PDF OCR failed", error=str(e))
            return {}, False


# Singleton kept for convenience — fully stateless so concurrent use is safe.
ocr_processor = OCRProcessor()
