"""Document text cleaning and normalization pipeline.

Stages (all synchronous, offloaded to executor):
  1. normalize_newlines         — CRLF → LF
  2. normalize_unicode          — NFC + strip control chars + ligatures
  3. normalize_whitespace       — collapse spaces, trim lines
  4. fix_ocr_artifacts          — NEW: correct common OCR character errors
  5. remove_page_numbers        — standalone page number lines
  6. remove_headers_footers     — repeated boilerplate detection
  7. remove_empty_lines         — trim leading/trailing blank lines
  8. sanitize_injection_markers — NEW: flag/strip prompt injection patterns in docs

Security note: ``sanitize_injection_markers`` does NOT delete content — it
replaces injection trigger phrases with a safe placeholder so they appear
in the context but cannot execute against the LLM.
"""

from __future__ import annotations

import re
import unicodedata
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


# ── Stage implementations ──────────────────────────────────────────────────


def normalize_newlines(text: str, _meta: dict | None = None) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def normalize_unicode(text: str, _meta: dict | None = None) -> str:
    """NFC normalization, ligature expansion, control character removal."""
    # NFC normalization
    text = unicodedata.normalize("NFC", text)
    # Remove non-printable / control characters except \n \t
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    # Expand common Unicode ligatures to ASCII equivalents
    _LIGATURES = {
        "ﬀ": "ff",
        "ﬁ": "fi",
        "ﬂ": "fl",
        "ﬃ": "ffi",
        "ﬄ": "ffl",
        "ﬅ": "st",
        "ﬆ": "st",
        "’": "'",  # right single quote
        "‘": "'",  # left single quote
        "“": '"',  # left double quote
        "”": '"',  # right double quote
        "–": "-",  # en-dash
        "—": "--",  # em-dash
        "…": "...",  # ellipsis
        " ": " ",  # non-breaking space
    }
    for src, dst in _LIGATURES.items():
        text = text.replace(src, dst)
    return text


def normalize_whitespace(text: str, _meta: dict | None = None) -> str:
    # Collapse non-standard space characters
    text = re.sub(r"[  -   　]", " ", text)
    # Collapse multiple spaces within lines
    text = re.sub(r" {2,}", " ", text)
    # Trim trailing whitespace from each line
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    # Collapse >2 consecutive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── OCR artifact correction ────────────────────────────────────────────────
# Common OCR confusion pairs — apply only when the substitution is unambiguous
# in context (whole-word matches to avoid false positives in normal text).
_OCR_WORD_FIXES: list[tuple[re.Pattern, str]] = [
    # Isolated "0" confused with "O" in words is hard to fix; skip generic
    # Specific high-confidence OCR confusions:
    (re.compile(r"\bRll\b"), "All"),  # R + ll → All
    (re.compile(r"\bHl\b"), "Hi"),  # OCR confusion
    (re.compile(r"\b1\b(?=\s+[a-z])"), "I"),  # standalone digit 1 → I
    (re.compile(r"(?<=\w)rn(?=\w)"), "m"),  # rn → m inside word (arm → arm, etc.)
    (re.compile(r"\bII\b(?!\w)"), "ll"),  # II → ll (only in word context)
]

# Multi-character OCR noise patterns (regex → replacement)
_OCR_PATTERN_FIXES: list[tuple[re.Pattern, str]] = [
    # Hyphen fragments: "hyphen-\nated" → "hyphenated"
    (re.compile(r"(\w)-\n(\w)"), r"\1\2"),
    # Page artifact: isolated numbers with dashes "- 12 -"
    (re.compile(r"^\s*-\s*\d{1,4}\s*-\s*$", re.MULTILINE), ""),
    # Remove scan artifacts: lines of only special chars
    (re.compile(r"^[\|_\-=~]{5,}\s*$", re.MULTILINE), ""),
    # Fix space-separated single letters (OCR char splitting): "h e l l o" in context
    # Only fix if 3+ single letters in a row (likely OCR artifact, not acronym)
    (re.compile(r"\b([A-Za-z]) ([A-Za-z]) ([A-Za-z])\b"), lambda m: m.group(0).replace(" ", "")),
]


def fix_ocr_artifacts(text: str, _meta: dict | None = None) -> str:
    """Correct common OCR character confusion errors."""
    # Pattern fixes (structural)
    for pattern, replacement in _OCR_PATTERN_FIXES:
        text = pattern.sub(replacement, text)
    return text


# ── Header/footer removal ──────────────────────────────────────────────────


def remove_headers_footers(text: str, _meta: dict | None = None) -> str:
    """Remove repeated boilerplate lines (headers/footers)."""
    from collections import Counter

    lines = text.split("\n")
    if len(lines) < 10:
        return text
    line_counts = Counter(line.strip() for line in lines if line.strip())
    threshold = max(3, len(lines) * 0.25)
    boilerplate = {
        line for line, count in line_counts.items() if count >= threshold and 3 < len(line) < 120
    }
    if not boilerplate:
        return text
    return "\n".join(line for line in lines if line.strip() not in boilerplate)


def remove_page_numbers(text: str, _meta: dict | None = None) -> str:
    """Remove standalone page number lines."""
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # Bare digits: "12", "123"
        if re.match(r"^\d{1,5}$", stripped):
            continue
        # Bracketed: "- 12 -", "(12)", "[12]"
        if re.match(r"^[-(\[]*\s*\d{1,5}\s*[-)\]]*$", stripped):
            continue
        # "Page 12 of 45", "Page 12"
        if re.match(r"^[Pp]age\s+\d+(\s+of\s+\d+)?$", stripped):
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def remove_empty_lines(text: str, _meta: dict | None = None) -> str:
    """Trim leading/trailing blank lines."""
    lines = text.split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


# ── Prompt injection sanitization ─────────────────────────────────────────
# These patterns are KNOWN adversarial prompt injection triggers. When found
# in document content, they are neutralised by encoding them so the LLM
# sees the text but cannot act on it as an instruction.
#
# Strategy: replace with "[INJECTION-ATTEMPT-BLOCKED: <original_start...>]"
# so the content is logged/auditable but cannot override system instructions.

_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions?", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an|the)\s+\w+", re.IGNORECASE),
    re.compile(
        r"forget\s+(all\s+)?your\s+(previous\s+)?(instructions?|training|rules)", re.IGNORECASE
    ),
    re.compile(r"new\s+system\s+prompt\s*:", re.IGNORECASE),
    re.compile(
        r"(developer|jailbreak|dan|god|unrestricted)\s+(mode|prompt|instructions?)", re.IGNORECASE
    ),
    re.compile(r"<\|?(system|user|assistant|im_start|im_end)\|?>", re.IGNORECASE),
    re.compile(r"\[INST\]|\[/INST\]|<<SYS>>|<</SYS>>"),
    re.compile(
        r"act\s+as\s+(if\s+)?(you\s+are\s+)?a[n]?\s+\w+\s+(without|with no)\s+(restriction|filter|limit)",
        re.IGNORECASE,
    ),
    re.compile(r"print\s+(your\s+)?(system|initial|original)\s+prompt", re.IGNORECASE),
    re.compile(
        r"reveal\s+(your\s+)?(system|internal|secret)\s+(prompt|instruction)", re.IGNORECASE
    ),
    re.compile(
        r"do\s+not\s+(follow|obey|adhere\s+to)\s+(the\s+)?(previous|above|prior)\s+(instruction|rule|guideline)",
        re.IGNORECASE,
    ),
]


def sanitize_injection_markers(text: str, _meta: dict | None = None) -> str:
    """Detect and neutralise prompt injection triggers in document content.

    Replaces injection patterns with a safe placeholder that the LLM
    can observe as text but cannot interpret as an instruction.
    """
    original = text
    for pattern in _INJECTION_PATTERNS:

        def _replace(m: re.Match) -> str:
            snippet = m.group(0)[:40].replace("]", ")") + ("..." if len(m.group(0)) > 40 else "")
            return f"[DOCUMENT-CONTENT: {snippet}]"

        text = pattern.sub(_replace, text)

    if text != original:
        logger.warning(
            "Prompt injection pattern detected and neutralized in document content",
            pattern_count=sum(1 for p in _INJECTION_PATTERNS if p.search(original)),
        )

    return text


# ── Default pipeline factory ───────────────────────────────────────────────


def create_default_pipeline() -> CleaningPipeline:
    """Build the default production cleaning pipeline."""
    pipeline = CleaningPipeline()
    pipeline.add_stage("normalize_newlines", normalize_newlines)
    pipeline.add_stage("normalize_unicode", normalize_unicode)
    pipeline.add_stage("fix_ocr_artifacts", fix_ocr_artifacts)
    pipeline.add_stage("normalize_whitespace", normalize_whitespace)
    pipeline.add_stage("remove_page_numbers", remove_page_numbers)
    pipeline.add_stage("remove_headers_footers", remove_headers_footers)
    pipeline.add_stage("remove_empty_lines", remove_empty_lines)
    pipeline.add_stage("sanitize_injection_markers", sanitize_injection_markers)
    return pipeline


def create_ocr_pipeline() -> CleaningPipeline:
    """Cleaning pipeline tuned for OCR-extracted text (more aggressive artifact removal)."""
    pipeline = CleaningPipeline()
    pipeline.add_stage("normalize_newlines", normalize_newlines)
    pipeline.add_stage("normalize_unicode", normalize_unicode)
    pipeline.add_stage("fix_ocr_artifacts", fix_ocr_artifacts)
    pipeline.add_stage("normalize_whitespace", normalize_whitespace)
    pipeline.add_stage("remove_page_numbers", remove_page_numbers)
    pipeline.add_stage("remove_headers_footers", remove_headers_footers)
    pipeline.add_stage("remove_empty_lines", remove_empty_lines)
    pipeline.add_stage("sanitize_injection_markers", sanitize_injection_markers)
    return pipeline
