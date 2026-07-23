"""JSON extractor — all sync calls offloaded via run_in_executor."""

from app.ingestion.executor import run_in_executor
from app.ingestion.extractors import (
    BaseExtractor, ExtractionResult, PageResult, extractor_registry,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


@extractor_registry.register("application/json")
class JsonExtractor(BaseExtractor):
    """Extract content from JSON files."""

    async def extract(self) -> ExtractionResult:
        def _do() -> ExtractionResult:
            import json
            r = ExtractionResult()
            content = self.file_path.read_text("utf-8", errors="replace")
            try:
                data = json.loads(content)
                root_type = type(data).__name__
                keys = list(data.keys()) if isinstance(data, dict) else []
                r.metadata.update({"title": self.file_path.stem, "root_type": root_type, "size_bytes": len(content), "element_count": len(data) if isinstance(data, (list, dict)) else 1, "top_level_keys": keys[:50] if keys else [], "has_nested_objects": any(isinstance(v, (dict, list)) for v in data.values()) if isinstance(data, dict) else False})
                formatted = json.dumps(data, indent=2, ensure_ascii=False)
                r.pages.append(PageResult(page_number=1, text=formatted, section_title=f"JSON Document: {self.file_path.name}"))
                r.text = formatted
            except json.JSONDecodeError as e:
                r.add_error(f"Invalid JSON: {e}")
                r.text = content
                r.pages.append(PageResult(page_number=1, text=content))
            return r
        return await run_in_executor(_do)

    async def extract_text(self) -> str:
        def _do() -> str:
            import json
            content = self.file_path.read_text("utf-8", errors="replace")
            try:
                data = json.loads(content)
                return json.dumps(data, indent=2, ensure_ascii=False)
            except json.JSONDecodeError:
                return content
        return await run_in_executor(_do)

    async def extract_metadata(self) -> dict:
        def _do() -> dict:
            import json
            content = self.file_path.read_text("utf-8", errors="replace")
            data = json.loads(content)
            keys = list(data.keys()) if isinstance(data, dict) else []
            return {"title": self.file_path.stem, "root_type": type(data).__name__, "size_bytes": len(content), "element_count": len(data) if isinstance(data, (list, dict)) else 1, "top_level_keys": keys[:50] if keys else [], "has_nested_objects": any(isinstance(v, (dict, list)) for v in data.values()) if isinstance(data, dict) else False}
        return await run_in_executor(_do)
