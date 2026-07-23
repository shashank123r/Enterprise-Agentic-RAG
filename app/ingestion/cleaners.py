"""Document text cleaning and normalization.

All synchronous processing offloaded via ``run_in_executor``.
"""

import re
from typing import Any

from app.core.logging import get_logger
from app.ingestion.executor import run_in_executor

logger = get_logger(__name__)


class CleaningPipeline:
    """Configurable document cleaning pipeline."""

    def __init__(self) -> None:
        self.stages: list[tuple[str, Any]] = []

    def add_stage(self, name: str, stage: Any) -> None:
        self.stages.append((name, stage))

    async def clean(self, text: str, metadata: dict | None = None) -> str:
        """Run all cleaning stages, offloaded to executor."""
        meta = metadata or {}

        def _do() -> str:
            result = text
            for name, stage in self.stages:
                try:
                    result = stage(result, meta)
                except Exception as e:
                    logger.warning("Cleaning stage failed", stage=name, error=str(e))
            return result

        return await run_in_executor(_do)


# ── Individual Cleaning Stages ─────────────────

def normalize_unicode(text: str, _metadata: dict | None = None) -> str:
    import unicodedata
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text


def normalize_whitespace(text: str, _metadata: dict | None = None) -> str:
    text = re.sub(r"[\u00a0\u1680\u2000-\u200a\u202f\u205f\u3000]", " ", text)
    text = re.sub(r" {2,}", " ", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def remove_headers_footers(text: str, _metadata: dict | None = None) -> str:
    lines = text.split("\n")
    if len(lines) < 10:
        return text
    from collections import Counter
    line_counts = Counter(lines)
    threshold = max(3, len(lines) * 0.3)
    boilerplate = {line for line, count in line_counts.items() if count > threshold and len(line.strip()) < 60}
    if not boilerplate:
        return text
    return "\n".join(line for line in lines if line not in boilerplate)


def remove_page_numbers(text: str, _metadata: dict | None = None) -> str:
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if re.match(r"^\d+$", stripped) and len(stripped) <= 6:
            continue
        if re.match(r"^[-(]*\s*\d+\s*[-)]*$", stripped):
            continue
        if re.match(r"^[Pp]age\s+\d+\s+of\s+\d+$", stripped):
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def normalize_newlines(text: str, _metadata: dict | None = None) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def remove_empty_lines(text: str, _metadata: dict | None = None) -> str:
    lines = text.split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def create_default_pipeline() -> CleaningPipeline:
    pipeline = CleaningPipeline()
    pipeline.add_stage("normalize_newlines", normalize_newlines)
    pipeline.add_stage("normalize_unicode", normalize_unicode)
    pipeline.add_stage("normalize_whitespace", normalize_whitespace)
    pipeline.add_stage("remove_page_numbers", remove_page_numbers)
    pipeline.add_stage("remove_headers_footers", remove_headers_footers)
    pipeline.add_stage("remove_empty_lines", remove_empty_lines)
    return pipeline
