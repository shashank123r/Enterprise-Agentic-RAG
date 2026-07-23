"""HTML extractor — all sync calls offloaded via run_in_executor."""

from app.ingestion.executor import run_in_executor
from app.ingestion.extractors import (
    BaseExtractor, ExtractionResult, PageResult, TableResult, extractor_registry,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


@extractor_registry.register("text/html")
class HtmlExtractor(BaseExtractor):
    """Extract structured content from HTML files."""

    async def extract(self) -> ExtractionResult:
        def _do() -> ExtractionResult:
            from bs4 import BeautifulSoup
            r = ExtractionResult()
            content = self.file_path.read_text("utf-8", errors="replace")
            soup = BeautifulSoup(content, "html.parser")
            meta_tags = {}
            for tag in soup.find_all("meta"):
                name = tag.get("name", tag.get("property", ""))
                content_val = tag.get("content", "")
                if name: meta_tags[name] = content_val
            r.metadata.update({"title": soup.title.string.strip() if soup.title else "", "meta_tags": meta_tags, "tag_count": len(soup.find_all()), "heading_count": len(soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])), "paragraph_count": len(soup.find_all("p")), "link_count": len(soup.find_all("a")), "image_count": len(soup.find_all("img")), "charset": str(soup.original_encoding or "")})

            section_idx = 0
            current_section, current_heading = [], None
            for el in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "pre", "blockquote"]):
                if el.name.startswith("h"):
                    if current_section:
                        r.pages.append(PageResult(page_number=section_idx, text="\n".join(current_section), section_title=current_heading))
                        section_idx += 1; current_section = []
                    current_heading = el.get_text(strip=True)
                    current_section.append(current_heading)
                else:
                    text = el.get_text(strip=True)
                    if text:
                        if el.name == "pre": text = f"```\n{text}\n```"
                        elif el.name == "li": text = f"  • {text}"
                        elif el.name == "blockquote": text = f"> {text}"
                        current_section.append(text)
            if current_section:
                r.pages.append(PageResult(page_number=section_idx, text="\n".join(current_section), section_title=current_heading))

            for t_idx, table_tag in enumerate(soup.find_all("table")):
                caption_tag = table_tag.find("caption")
                cap = caption_tag.get_text(strip=True) if caption_tag else None
                thead, tbody = table_tag.find("thead"), table_tag.find("tbody") or table_tag
                headers = [th.get_text(strip=True) for th in thead.find_all("th")] if thead else []
                if not headers and table_tag.find("tr"):
                    headers = [th.get_text(strip=True) for th in table_tag.find("tr").find_all(["th", "td"])]
                rows = [[td.get_text(strip=True) for td in row.find_all(["td", "th"])] for row in tbody.find_all("tr") if [td.get_text(strip=True) for td in row.find_all(["td", "th"])]]
                if headers and rows:
                    r.tables.append(TableResult(page_number=None, table_index=t_idx, headers=headers, rows=rows, caption=cap))
            r.text = soup.get_text(separator="\n", strip=True)
            return r
        return await run_in_executor(_do)

    async def extract_text(self) -> str:
        def _do() -> str:
            from bs4 import BeautifulSoup
            content = self.file_path.read_text("utf-8", errors="replace")
            soup = BeautifulSoup(content, "html.parser")
            return soup.get_text(separator="\n", strip=True)
        return await run_in_executor(_do)

    async def extract_metadata(self) -> dict:
        def _do() -> dict:
            from bs4 import BeautifulSoup
            content = self.file_path.read_text("utf-8", errors="replace")
            soup = BeautifulSoup(content, "html.parser")
            meta_tags = {}
            for tag in soup.find_all("meta"):
                name = tag.get("name", tag.get("property", ""))
                content_val = tag.get("content", "")
                if name: meta_tags[name] = content_val
            return {"title": soup.title.string.strip() if soup.title else "", "meta_tags": meta_tags, "tag_count": len(soup.find_all()), "heading_count": len(soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])), "paragraph_count": len(soup.find_all("p")), "link_count": len(soup.find_all("a")), "image_count": len(soup.find_all("img")), "charset": str(soup.original_encoding or "")}
        return await run_in_executor(_do)
