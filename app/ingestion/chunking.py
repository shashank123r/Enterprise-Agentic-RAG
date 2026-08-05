"""Enterprise document chunking pipeline.

Strategies:
  - SemanticChunker       — sentence-boundary aware, adaptive overlap
  - HeadingAwareChunker   — section-based, full hierarchy tracking
  - MarkdownAwareChunker  — heading+code-block aware
  - TableAwareChunker     — atomic table chunks
  - CodeAwareChunker      — NEW: function/class boundary splitting
  - AdaptiveChunker       — content-density adaptive sizing
  - ParentChildChunker    — hierarchical parent+child relationships
  - OCRChunker            — NEW: noise-tolerant OCR output chunking

All chunkers preserve rich metadata (page, section hierarchy, chunk type,
language hint, content hash) and attach it to every ChunkResult.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Sentence splitter ──────────────────────────────────────────────────────
# Handles abbreviations (e.g., Dr., Fig., vs., i.e.) and avoids splitting on
# decimal numbers (3.14), section references (Sec. 3.1), etc.
_ABBREV = frozenset(
    "dr mr mrs ms prof sr jr rev gen lt col sgt pvt est etc vs eg ie "
    "fig fig no vol pp ed eds sec sect ch pt approx approx dept govt "
    "inc corp ltd llc jan feb mar apr jun jul aug sep oct nov dec "
    "mon tue wed thu fri sat sun".split()
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=[.!?])\s+(?=[A-Z\"‘“¿¡])")


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences, respecting common abbreviations."""
    raw = _SENTENCE_SPLIT_RE.split(text)
    result: list[str] = []
    buffer = ""
    for part in raw:
        if buffer:
            combined = buffer + " " + part
        else:
            combined = part

        # Check if the last word before '.' is an abbreviation
        last_word_match = re.search(r"\b(\w+)\.\s*$", buffer.lower())
        if last_word_match and last_word_match.group(1) in _ABBREV:
            buffer = combined
            continue

        result.append(combined.strip())
        buffer = ""

    if buffer:
        result.append(buffer.strip())

    return [s for s in result if s]


# ── ChunkResult ────────────────────────────────────────────────────────────


class ChunkResult:
    """Result of a single chunk operation with full metadata."""

    def __init__(
        self,
        content: str,
        chunk_index: int,
        chunk_type: str = "text",
        page_number: int | None = None,
        section_title: str | None = None,
        section_hierarchy: list[str] | None = None,
        parent_chunk_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        language: str | None = None,
        code_language: str | None = None,
    ) -> None:
        self.content = content
        self.chunk_index = chunk_index
        self.chunk_type = chunk_type
        self.page_number = page_number
        self.section_title = section_title
        self.section_hierarchy = section_hierarchy or []
        self.parent_chunk_id = parent_chunk_id
        self.metadata = metadata or {}
        self.language = language
        self.code_language = code_language  # "python", "sql", "javascript", etc.

    @property
    def content_checksum(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()[:16]

    @property
    def char_count(self) -> int:
        return len(self.content)

    @property
    def token_count_approx(self) -> int:
        """Approximate token count — use TokenBudget.count_tokens() for precision."""
        return len(self.content) // 4


# ── Base strategy ──────────────────────────────────────────────────────────


class ChunkingStrategy:
    def __init__(
        self,
        max_chunk_size: int = 1024,
        min_chunk_size: int = 100,
        overlap: int = 100,
    ) -> None:
        self.max_chunk_size = max_chunk_size
        self.min_chunk_size = min_chunk_size
        self.overlap = overlap

    async def chunk(self, text: str, metadata: dict[str, Any] | None = None) -> list[ChunkResult]:
        raise NotImplementedError


# ── SemanticChunker ────────────────────────────────────────────────────────


class SemanticChunker(ChunkingStrategy):
    """Chunks at sentence boundaries with adaptive overlap.

    Overlap adapts to sentence length: shorter sentences yield less overlap
    to avoid redundant context; longer sentences preserve more.
    """

    async def chunk(self, text: str, metadata: dict[str, Any] | None = None) -> list[ChunkResult]:
        sentences = _split_sentences(text)
        if not sentences:
            return []

        chunks: list[ChunkResult] = []
        current: list[str] = []
        current_size = 0

        for sentence in sentences:
            slen = len(sentence)
            if current_size + slen > self.max_chunk_size and current:
                chunks.append(self._make(current, len(chunks), metadata))
                # Adaptive overlap: keep sentences from the tail that fit overlap budget
                overlap_sentences = self._adaptive_overlap(current)
                current = overlap_sentences
                current_size = sum(len(s) for s in current)

            current.append(sentence)
            current_size += slen

        if current and current_size >= self.min_chunk_size:
            chunks.append(self._make(current, len(chunks), metadata))

        return chunks

    def _make(self, sentences: list[str], idx: int, metadata: dict | None) -> ChunkResult:
        return ChunkResult(
            content=" ".join(sentences),
            chunk_index=idx,
            chunk_type="semantic",
            metadata=metadata or {},
        )

    def _adaptive_overlap(self, sentences: list[str]) -> list[str]:
        """Return the tail of a sentence list that fits the overlap budget."""
        budget = self.overlap
        tail: list[str] = []
        for s in reversed(sentences):
            if len(s) > budget:
                break
            tail.insert(0, s)
            budget -= len(s)
        return tail


# ── HeadingAwareChunker ────────────────────────────────────────────────────


class HeadingAwareChunker(ChunkingStrategy):
    """Splits by headings, tracking full section hierarchy."""

    _HEADING_RE = re.compile(
        r"^(#{1,6})\s+(.+)$"  # Markdown headings
        r"|^(.+)\n([=-]{3,})$",  # Setext headings
        re.MULTILINE,
    )

    async def chunk(self, text: str, metadata: dict[str, Any] | None = None) -> list[ChunkResult]:
        sections = self._parse_sections(text)
        chunks: list[ChunkResult] = []
        hierarchy: list[str] = []

        for level, heading, body in sections:
            if not body.strip():
                continue
            # Update hierarchy
            if level is not None:
                hierarchy = hierarchy[: level - 1] + [heading or ""]

            if len(body) > self.max_chunk_size:
                sub = SemanticChunker(
                    max_chunk_size=self.max_chunk_size, min_chunk_size=self.min_chunk_size
                )
                for sub_chunk in await sub.chunk(body, metadata):
                    sub_chunk.section_title = heading
                    sub_chunk.section_hierarchy = list(hierarchy)
                    sub_chunk.chunk_type = "section"
                    sub_chunk.chunk_index = len(chunks)
                    chunks.append(sub_chunk)
            else:
                chunks.append(
                    ChunkResult(
                        content=body.strip(),
                        chunk_index=len(chunks),
                        chunk_type="section",
                        section_title=heading,
                        section_hierarchy=list(hierarchy),
                        metadata=metadata or {},
                    )
                )

        return chunks

    def _parse_sections(self, text: str) -> list[tuple[int | None, str | None, str]]:
        """Parse text into (level, heading, body) tuples."""
        lines = text.split("\n")
        sections: list[tuple[int | None, str | None, str]] = []
        current_body: list[str] = []
        current_heading: str | None = None
        current_level: int | None = None

        def flush():
            if current_body or current_heading:
                sections.append((current_level, current_heading, "\n".join(current_body)))

        for i, line in enumerate(lines):
            # Markdown # heading
            m_atx = re.match(r"^(#{1,6})\s+(.+)$", line)
            # Setext heading
            m_set = re.match(r"^([=-]{3,})$", line) if i > 0 else None

            if m_atx:
                flush()
                current_body = []
                current_level = len(m_atx.group(1))
                current_heading = m_atx.group(2).strip()
            elif m_set and current_body:
                # The previous line is the heading text
                heading_text = current_body.pop()
                flush()
                current_body = []
                current_level = 1 if line[0] == "=" else 2
                current_heading = heading_text.strip()
            else:
                current_body.append(line)

        flush()
        return sections


# ── MarkdownAwareChunker ───────────────────────────────────────────────────


class MarkdownAwareChunker(ChunkingStrategy):
    """Chunks markdown text at heading boundaries, keeping code blocks intact."""

    async def chunk(self, text: str, metadata: dict[str, Any] | None = None) -> list[ChunkResult]:
        lines = text.split("\n")
        chunks: list[ChunkResult] = []
        current: list[str] = []
        current_size = 0
        current_heading: str | None = None
        in_code_block = False
        code_lang: str | None = None

        for line in lines:
            # Detect code fence
            fence_match = re.match(r"^(`{3,}|~{3,})\s*(\w+)?", line)
            if fence_match:
                in_code_block = not in_code_block
                if in_code_block:
                    code_lang = fence_match.group(2) or None

            heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if heading_match and not in_code_block:
                # Flush existing content
                if current and current_size >= self.min_chunk_size:
                    chunks.append(
                        ChunkResult(
                            content="\n".join(current),
                            chunk_index=len(chunks),
                            chunk_type="markdown_section",
                            section_title=current_heading,
                            metadata=metadata or {},
                        )
                    )
                    current = []
                    current_size = 0
                current_heading = heading_match.group(2).strip()

            current.append(line)
            current_size += len(line) + 1

        if current:
            chunks.append(
                ChunkResult(
                    content="\n".join(current),
                    chunk_index=len(chunks),
                    chunk_type="markdown_section",
                    section_title=current_heading,
                    metadata=metadata or {},
                )
            )

        return chunks


# ── TableAwareChunker ──────────────────────────────────────────────────────


class TableAwareChunker(ChunkingStrategy):
    """Chunks text, preserving tables as atomic units."""

    _TABLE_LINE_RE = re.compile(r"^\s*\|.+\|\s*$")

    async def chunk(self, text: str, metadata: dict[str, Any] | None = None) -> list[ChunkResult]:
        lines = text.split("\n")
        chunks: list[ChunkResult] = []
        text_buf: list[str] = []
        table_buf: list[str] = []
        in_table = False

        def flush_text() -> None:
            content = "\n".join(text_buf).strip()
            if content and len(content) >= self.min_chunk_size:
                chunks.append(
                    ChunkResult(
                        content=content,
                        chunk_index=len(chunks),
                        chunk_type="text",
                        metadata=metadata or {},
                    )
                )
            text_buf.clear()

        def flush_table() -> None:
            content = "\n".join(table_buf).strip()
            if content:
                chunks.append(
                    ChunkResult(
                        content=content,
                        chunk_index=len(chunks),
                        chunk_type="table",
                        metadata=metadata or {},
                    )
                )
            table_buf.clear()

        for line in lines:
            is_table = bool(self._TABLE_LINE_RE.match(line))
            if is_table:
                if text_buf:
                    flush_text()
                table_buf.append(line)
                in_table = True
            else:
                if in_table:
                    flush_table()
                    in_table = False
                text_buf.append(line)

        if in_table:
            flush_table()
        elif text_buf:
            flush_text()

        return chunks


# ── CodeAwareChunker ───────────────────────────────────────────────────────


class CodeAwareChunker(ChunkingStrategy):
    """Chunks code files at function/class boundaries.

    Detects:
    - Python: def, class, async def at module level
    - JavaScript/TypeScript: function, const/let/var arrow, class
    - SQL: CREATE, SELECT statement blocks
    - Generic: falls back to blank-line splitting with size limit
    """

    # Language-specific top-level function/class boundary patterns
    _BOUNDARIES: dict[str, re.Pattern] = {
        "python": re.compile(r"^(async\s+def|def|class)\s+\w+", re.MULTILINE),
        "javascript": re.compile(
            r"^(export\s+)?(async\s+)?function\s+\w+|^(export\s+)?(const|let|var)\s+\w+\s*=\s*(async\s+)?\(|^class\s+\w+",
            re.MULTILINE,
        ),
        "typescript": re.compile(
            r"^(export\s+)?(async\s+)?function\s+\w+|^(export\s+)?(const|let|var)\s+\w+|^(export\s+)?(abstract\s+)?class\s+\w+|^(export\s+)?interface\s+\w+|^(export\s+)?type\s+\w+\s*=",
            re.MULTILINE,
        ),
        "sql": re.compile(
            r"^(CREATE|ALTER|DROP|INSERT|SELECT|UPDATE|DELETE|WITH)\b", re.MULTILINE | re.IGNORECASE
        ),
        "java": re.compile(
            r"^(public|private|protected|static)?\s*(class|interface|enum|void|[A-Z]\w+)\s+\w+",
            re.MULTILINE,
        ),
        "go": re.compile(r"^func\s+(\(\w+\s+\*?\w+\)\s+)?\w+\s*\(", re.MULTILINE),
        "rust": re.compile(
            r"^(pub\s+)?(async\s+)?fn\s+\w+|^(pub\s+)?(struct|enum|trait|impl)\s+\w+", re.MULTILINE
        ),
    }

    def __init__(self, *args: Any, detected_language: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._detected_language = detected_language

    async def chunk(self, text: str, metadata: dict[str, Any] | None = None) -> list[ChunkResult]:
        lang = self._detected_language or self._detect_language(text)
        pattern = self._BOUNDARIES.get(lang)

        if pattern:
            return self._chunk_by_pattern(text, pattern, lang, metadata)
        # Generic: split on blank lines with size enforcement
        return self._chunk_by_blank_lines(text, lang, metadata)

    def _chunk_by_pattern(
        self,
        text: str,
        pattern: re.Pattern,
        lang: str,
        metadata: dict | None,
    ) -> list[ChunkResult]:
        """Split at language-specific boundary pattern."""
        positions = [m.start() for m in pattern.finditer(text)]
        if not positions:
            return self._chunk_by_blank_lines(text, lang, metadata)

        # Add start and end sentinel
        split_points = [0] + positions + [len(text)]
        chunks: list[ChunkResult] = []
        for i in range(1, len(split_points)):
            segment = text[split_points[i - 1] : split_points[i]].strip()
            if not segment or len(segment) < self.min_chunk_size:
                continue
            if len(segment) > self.max_chunk_size:
                # Recursively split large functions at blank lines
                for sub in self._chunk_by_blank_lines(segment, lang, metadata):
                    sub.chunk_index = len(chunks)
                    chunks.append(sub)
            else:
                chunks.append(
                    ChunkResult(
                        content=segment,
                        chunk_index=len(chunks),
                        chunk_type="code",
                        code_language=lang,
                        metadata=metadata or {},
                    )
                )
        return chunks

    def _chunk_by_blank_lines(
        self, text: str, lang: str, metadata: dict | None
    ) -> list[ChunkResult]:
        """Generic split on blank lines with max_chunk_size enforcement."""
        paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
        chunks: list[ChunkResult] = []
        current: list[str] = []
        current_size = 0

        for para in paragraphs:
            if current_size + len(para) > self.max_chunk_size and current:
                chunks.append(
                    ChunkResult(
                        content="\n\n".join(current),
                        chunk_index=len(chunks),
                        chunk_type="code",
                        code_language=lang or None,
                        metadata=metadata or {},
                    )
                )
                current = []
                current_size = 0
            current.append(para)
            current_size += len(para)

        if current:
            chunks.append(
                ChunkResult(
                    content="\n\n".join(current),
                    chunk_index=len(chunks),
                    chunk_type="code",
                    code_language=lang or None,
                    metadata=metadata or {},
                )
            )
        return chunks

    @staticmethod
    def _detect_language(text: str) -> str:
        """Heuristic language detection from code content."""
        sample = text[:2000].lower()
        signals: dict[str, int] = {}
        if re.search(r"\bdef \w+\(|import \w+|print\(|if __name__", sample):
            signals["python"] = signals.get("python", 0) + 3
        if re.search(r"function\s+\w+\s*\(|const\s+\w+\s*=|let\s+\w+|=>\s*\{", sample):
            signals["javascript"] = signals.get("javascript", 0) + 3
        if re.search(r"interface\s+\w+|type\s+\w+\s*=|:\s*string|:\s*number|tsx?$", sample):
            signals["typescript"] = signals.get("typescript", 0) + 3
        if re.search(r"\bselect\b.+\bfrom\b|\bcreate\s+table\b|\binsert\s+into\b", sample):
            signals["sql"] = signals.get("sql", 0) + 3
        if re.search(r"\bpackage\s+\w+|\bimport\s+\"|\bfunc\s+\w+\s*\(", sample):
            signals["go"] = signals.get("go", 0) + 3
        if re.search(r"\bfn\s+\w+\s*\(|let mut\s+\w+|impl\s+\w+\s*\{|use\s+\w+::", sample):
            signals["rust"] = signals.get("rust", 0) + 3
        if signals:
            return max(signals, key=lambda k: signals[k])
        return "generic"


# ── OCRChunker ─────────────────────────────────────────────────────────────


class OCRChunker(ChunkingStrategy):
    """Noise-tolerant chunker for OCR-extracted text.

    OCR output frequently contains:
    - Spurious line breaks mid-sentence
    - Inconsistent paragraph breaks
    - Mixed quality (some pages clear, others garbled)

    Strategy:
    1. Join lines that don't end with sentence-terminal punctuation
    2. Normalize to paragraphs
    3. Apply SemanticChunker on the normalized output
    """

    async def chunk(self, text: str, metadata: dict[str, Any] | None = None) -> list[ChunkResult]:
        normalized = self._normalize_ocr_text(text)
        inner = SemanticChunker(
            max_chunk_size=self.max_chunk_size,
            min_chunk_size=self.min_chunk_size,
            overlap=self.overlap,
        )
        chunks = await inner.chunk(normalized, metadata)
        for c in chunks:
            c.chunk_type = "ocr_text"
        return chunks

    @staticmethod
    def _normalize_ocr_text(text: str) -> str:
        """Merge spurious mid-sentence line breaks introduced by OCR."""
        lines = text.split("\n")
        paragraphs: list[str] = []
        buffer = ""

        for line in lines:
            stripped = line.strip()
            if not stripped:
                if buffer:
                    paragraphs.append(buffer)
                    buffer = ""
                continue

            # If the previous line ended with sentence-terminal punctuation OR
            # this line starts with a capital letter after a non-terminal,
            # start a new paragraph
            if buffer:
                last_char = buffer[-1] if buffer else ""
                if last_char in ".!?":
                    paragraphs.append(buffer)
                    buffer = stripped
                else:
                    buffer = buffer + " " + stripped
            else:
                buffer = stripped

        if buffer:
            paragraphs.append(buffer)

        return "\n\n".join(paragraphs)


# ── AdaptiveChunker ────────────────────────────────────────────────────────


class AdaptiveChunker(ChunkingStrategy):
    """Adjusts chunk size based on content density.

    Dense (code, tables) → smaller chunks for precision.
    Sparse (narrative) → larger chunks for context richness.
    """

    _DENSE_RE = [
        re.compile(r"^\s{4,}\S"),  # Indented code
        re.compile(r"^\|.+\|$"),  # Table rows
        re.compile(r"^\d+[.\)]\s+\S"),  # Numbered lists
        re.compile(r"^[-*]\s+\S"),  # Bullet lists
        re.compile(r"^```"),  # Code fence
    ]

    async def chunk(self, text: str, metadata: dict[str, Any] | None = None) -> list[ChunkResult]:
        paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
        chunks: list[ChunkResult] = []
        current: list[str] = []
        current_size = 0

        for para in paragraphs:
            density = self._density(para)
            adaptive_max = int(self.max_chunk_size * density)

            if current_size + len(para) > adaptive_max and current:
                chunks.append(
                    ChunkResult(
                        content="\n\n".join(current),
                        chunk_index=len(chunks),
                        chunk_type="adaptive",
                        metadata=metadata or {},
                    )
                )
                current = []
                current_size = 0

            current.append(para)
            current_size += len(para)

        if current:
            chunks.append(
                ChunkResult(
                    content="\n\n".join(current),
                    chunk_index=len(chunks),
                    chunk_type="adaptive",
                    metadata=metadata or {},
                )
            )

        return chunks

    def _density(self, text: str) -> float:
        lines = text.split("\n")
        if not lines:
            return 1.0
        dense = sum(1 for l in lines if any(p.match(l) for p in self._DENSE_RE))
        ratio = dense / len(lines)
        return max(0.3, 1.0 - ratio * 0.7)


# ── ParentChildChunker ─────────────────────────────────────────────────────


class ParentChildChunker(ChunkingStrategy):
    """Creates hierarchical parent-child chunks.

    Parents: large, context-rich (retrieved for surrounding context).
    Children: small, precise (retrieved for exact answer).
    """

    def __init__(
        self,
        parent_chunk_size: int = 2048,
        child_chunk_size: int = 512,
        child_overlap: int = 64,
    ) -> None:
        super().__init__(max_chunk_size=parent_chunk_size, min_chunk_size=100)
        self.parent_chunk_size = parent_chunk_size
        self.child_chunk_size = child_chunk_size
        self.child_overlap = child_overlap

    async def chunk(self, text: str, metadata: dict[str, Any] | None = None) -> list[ChunkResult]:
        meta = metadata or {}
        parent_chunker = HeadingAwareChunker(max_chunk_size=self.parent_chunk_size)
        parents = await parent_chunker.chunk(text, meta)

        all_chunks: list[ChunkResult] = []
        child_chunker = SemanticChunker(
            max_chunk_size=self.child_chunk_size, overlap=self.child_overlap
        )

        for parent in parents:
            parent.chunk_index = len(all_chunks)
            parent_id = parent.content_checksum
            all_chunks.append(parent)

            children = await child_chunker.chunk(parent.content, meta)
            for child in children:
                child.parent_chunk_id = parent_id
                child.chunk_type = "child"
                child.section_title = parent.section_title
                child.section_hierarchy = list(parent.section_hierarchy)
                child.chunk_index = len(all_chunks)
                all_chunks.append(child)

        return all_chunks


# ── ChunkingPipeline ───────────────────────────────────────────────────────


class ChunkingPipeline:
    """Orchestrates multiple chunking strategies with MIME-type-aware auto-selection."""

    def __init__(self) -> None:
        self.strategies: dict[str, ChunkingStrategy] = {
            "semantic": SemanticChunker(),
            "heading": HeadingAwareChunker(),
            "markdown": MarkdownAwareChunker(),
            "table_aware": TableAwareChunker(),
            "code": CodeAwareChunker(),
            "ocr": OCRChunker(),
            "adaptive": AdaptiveChunker(),
            "parent_child": ParentChildChunker(),
        }

    async def chunk_document(
        self,
        text: str,
        strategy: str = "adaptive",
        metadata: dict[str, Any] | None = None,
        mime_type: str | None = None,
        detected_language: str | None = None,
    ) -> list[ChunkResult]:
        """Chunk a document using the selected or auto-detected strategy.

        Args:
            text: Document text (pre-cleaned).
            strategy: Chunking strategy name, or "auto" to select by mime_type.
            metadata: Metadata dict attached to every chunk.
            mime_type: MIME type for auto-selection.
            detected_language: Programming language hint for code chunking.

        Returns:
            List of ChunkResult objects.
        """
        if strategy == "auto" and mime_type:
            strategy = self._auto_select(mime_type, text)

        chunker = self.strategies.get(strategy)
        if chunker is None:
            logger.warning("Unknown chunking strategy, falling back to adaptive", strategy=strategy)
            chunker = self.strategies["adaptive"]

        # Pass detected_language to CodeAwareChunker
        if isinstance(chunker, CodeAwareChunker) and detected_language:
            chunker = CodeAwareChunker(
                max_chunk_size=chunker.max_chunk_size,
                min_chunk_size=chunker.min_chunk_size,
                detected_language=detected_language,
            )

        chunks = await chunker.chunk(text, metadata)

        # Post-process: remove empty chunks, re-index
        valid = [
            c for c in chunks if c.content.strip() and len(c.content) >= chunker.min_chunk_size
        ]
        for i, c in enumerate(valid):
            c.chunk_index = i

        return valid

    def _auto_select(self, mime_type: str, text: str) -> str:
        strategy_map = {
            "text/markdown": "markdown",
            "text/csv": "table_aware",
            "text/html": "heading",
            "text/x-python": "code",
            "text/javascript": "code",
            "text/typescript": "code",
            "application/json": "semantic",
            "application/pdf": "adaptive",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "heading",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation": "heading",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "table_aware",
        }
        strategy = strategy_map.get(mime_type)
        if strategy:
            return strategy

        # Infer code from content heuristics
        if self._looks_like_code(text):
            return "code"

        return "adaptive"

    @staticmethod
    def _looks_like_code(text: str) -> bool:
        sample = text[:1000]
        code_signals = [
            bool(re.search(r"^\s*(def|class|import|from)\s+\w+", sample, re.MULTILINE)),
            bool(re.search(r"^\s*(function|const|let|var)\s+\w+", sample, re.MULTILINE)),
            bool(
                re.search(
                    r"^\s*(SELECT|CREATE|INSERT|UPDATE)\s+\w+", sample, re.MULTILINE | re.IGNORECASE
                )
            ),
            sample.count("{") > 5 and sample.count("}") > 5,
        ]
        return sum(code_signals) >= 2


chunking_pipeline = ChunkingPipeline()
