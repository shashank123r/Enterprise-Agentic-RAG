"""Markdown extractor — sync calls offloaded via run_in_executor."""

import re

import markdown as md_lib

from app.ingestion.executor import run_in_executor
from app.ingestion.extractors import (
    BaseExtractor,
    ExtractionResult,
    PageResult,
    TableResult,
    extractor_registry,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


@extractor_registry.register("text/markdown")
class MarkdownExtractor(BaseExtractor):
    """Extract structured content from Markdown files."""

    async def extract(self) -> ExtractionResult:
        def _do() -> ExtractionResult:
            content = self.file_path.read_text("utf-8")
            r = ExtractionResult()
            html = md_lib.markdown(content)
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")
            headings = [tag.get_text(strip=True) for tag in soup.find_all(["h1", "h2", "h3", "h4"])]
            r.metadata.update(
                {
                    "title": headings[0] if headings else self.file_path.stem,
                    "heading_count": len(headings),
                    "headings": headings,
                    "code_blocks": len(soup.find_all("code")),
                    "paragraphs": len(soup.find_all("p")),
                    "lists": len(soup.find_all(["ul", "ol"])),
                    "char_count": len(content),
                    "line_count": len(content.splitlines()),
                }
            )

            sections = re.split(r"^(#{1,4})\s+(.+)$", content, flags=re.MULTILINE)
            page_text = (
                [] if not sections or not sections[0].strip() else [(None, sections[0].strip())]
            )
            for i in range(1, len(sections) - 1, 3):
                if i + 1 < len(sections):
                    page_text.append(
                        (
                            sections[i + 1].strip(),
                            sections[i + 2].strip() if i + 2 < len(sections) else "",
                        )
                    )
            for idx, (heading, body) in enumerate(page_text):
                r.pages.append(PageResult(page_number=idx + 1, text=body, section_title=heading))

            table_pattern = re.compile(
                r"^\|(.+)\|\s*$\n^\|[-| :]+\|\s*$\n((?:^\|.+\|\s*$\n?)*)", re.MULTILINE
            )
            for t_idx, match in enumerate(table_pattern.finditer(content)):
                headers = [h.strip() for h in match.group(1).split("|")]
                rows = [
                    [c.strip() for c in line.strip()[1:-1].split("|")]
                    for line in match.group(2).strip().split("\n")
                    if line.strip()
                ]
                r.tables.append(
                    TableResult(page_number=None, table_index=t_idx, headers=headers, rows=rows)
                )
            r.text = content
            return r

        return await run_in_executor(_do)

    async def extract_text(self) -> str:
        def _do() -> str:
            return self.file_path.read_text("utf-8")

        return await run_in_executor(_do)

    async def extract_metadata(self) -> dict:
        def _do() -> dict:
            content = self.file_path.read_text("utf-8")
            html = md_lib.markdown(content)
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")
            headings = [tag.get_text(strip=True) for tag in soup.find_all(["h1", "h2", "h3", "h4"])]
            return {
                "title": headings[0] if headings else self.file_path.stem,
                "heading_count": len(headings),
                "headings": headings,
                "code_blocks": len(soup.find_all("code")),
                "paragraphs": len(soup.find_all("p")),
                "lists": len(soup.find_all(["ul", "ol"])),
                "char_count": len(content),
                "line_count": len(content.splitlines()),
            }

        return await run_in_executor(_do)
