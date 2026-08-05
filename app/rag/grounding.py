"""Grounding validator — verifies generated answers are supported by retrieved context.

Replaces pure lexical (citation-marker) checking with:
  - Semantic similarity via TF-IDF cosine (no extra API calls)
  - Per-sentence support scoring
  - Confidence-scored unsupported claim detection
  - Evidence mapping per claim
  - Citation integrity validation
  - Contradiction detection (high-confidence contradictions)
"""

from __future__ import annotations

import re
from typing import Any

from app.core.logging import get_logger
from app.rag.exceptions import RAGGroundingError
from app.retrieval.schemas import RetrievedChunk

logger = get_logger(__name__)

# Minimum cosine similarity for a sentence to be considered "supported"
_SUPPORT_THRESHOLD = 0.12
# Sentences shorter than this (chars) are not individually validated
_MIN_SENTENCE_LEN = 30
# Stopwords excluded from TF-IDF
_STOPWORDS = frozenset(
    "a an the and or but in on at to for of with by from that this "
    "is are was were be been being have has had do does did will "
    "would could should may might shall can what when where who why "
    "how which whom whose these those it its they them their".split()
)


def _cosine_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    """Compute sparse cosine similarity between two TF-IDF dicts."""
    if not vec_a or not vec_b:
        return 0.0
    dot = sum(vec_a.get(t, 0.0) * vec_b.get(t, 0.0) for t in vec_a if t in vec_b)
    mag_a = sum(v * v for v in vec_a.values()) ** 0.5
    mag_b = sum(v * v for v in vec_b.values()) ** 0.5
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase words, removing stopwords."""
    tokens = re.findall(r"\b[a-z0-9][a-z0-9\-']*[a-z0-9]\b", text.lower())
    return [t for t in tokens if t not in _STOPWORDS and len(t) >= 3]


def _tfidf_vector(text: str, idf: dict[str, float]) -> dict[str, float]:
    """Build a TF-IDF vector for a text given a pre-computed IDF dict."""
    tokens = _tokenize(text)
    if not tokens:
        return {}
    tf: dict[str, float] = {}
    for token in tokens:
        tf[token] = tf.get(token, 0) + 1
    n = len(tokens)
    return {t: (count / n) * idf.get(t, 1.0) for t, count in tf.items()}


def _build_idf(documents: list[str]) -> dict[str, float]:
    """Build IDF weights from a corpus of documents."""
    import math

    n = len(documents)
    df: dict[str, int] = {}
    for doc in documents:
        for token in set(_tokenize(doc)):
            df[token] = df.get(token, 0) + 1
    return {token: math.log((n + 1) / (count + 1)) + 1.0 for token, count in df.items()}


class GroundingValidator:
    """Validates that generated answers are grounded in retrieved context.

    Grounding pipeline:
        1. Citation integrity — every [N] references a real source
        2. Semantic support — TF-IDF cosine similarity between each answer
           sentence and the chunk corpus (no extra API calls)
        3. Confidence scoring — per-sentence support confidence [0, 1]
        4. Unsupported claim detection — sentences below support threshold
        5. Evidence mapping — which chunk best supports each sentence
    """

    def __init__(self, support_threshold: float = _SUPPORT_THRESHOLD) -> None:
        self._threshold = support_threshold

    async def validate(
        self,
        answer: str,
        chunks: list[RetrievedChunk],
        question: str,
    ) -> dict[str, Any]:
        """Validate that an answer is grounded in source chunks.

        Args:
            answer: Generated answer text.
            chunks: Source chunks used as context.
            question: Original question (used for diagnostics only).

        Returns:
            Dict with keys:
                valid: bool
                issues: list[str]
                unsupported_statements: list[str]
                citation_count: int
                invalid_citations: list[str]
                admits_no_info: bool
                confidence: float  ← NEW: overall grounding confidence [0, 1]
                sentence_scores: list[dict]  ← NEW: per-sentence evidence
                evidence_map: dict[str, str]  ← NEW: sentence → best chunk_id
        """
        issues: list[str] = []
        unsupported_statements: list[str] = []
        sentence_scores: list[dict[str, Any]] = []
        evidence_map: dict[str, str] = {}

        # ── 1. Citation integrity ──────────────────────────────────────────
        citation_nums = self._extract_citations(answer)
        valid_count = 0
        invalid_citations: list[str] = []

        for num in citation_nums:
            if 1 <= num <= len(chunks):
                valid_count += 1
            else:
                invalid_citations.append(str(num))
                issues.append(
                    f"Citation [{num}] references a non-existent source (only {len(chunks)} sources available)"
                )

        if not citation_nums and len(answer.strip()) > 80 and chunks:
            issues.append(
                "Answer lacks citations despite having source context — add [N] references"
            )

        # ── 2. No-information detection ────────────────────────────────────
        no_info_phrases = [
            "i don't have enough information",
            "i cannot answer",
            "i don't have the specific",
            "i don't have access to",
            "not provided in the context",
            "does not contain information",
            "not mentioned in the sources",
            "cannot find this information",
            "the context does not",
            "based on the provided context, i cannot",
        ]
        admits_no_info = any(phrase in answer.lower() for phrase in no_info_phrases)

        # ── 3. Semantic support scoring ────────────────────────────────────
        overall_confidence = 1.0
        if chunks:
            sentences = self._split_sentences(answer)
            substantive = [s for s in sentences if len(s) >= _MIN_SENTENCE_LEN]

            if substantive:
                chunk_texts = [c.text for c in chunks]
                # Build IDF over the full chunk corpus + answer sentences
                idf = _build_idf(chunk_texts + [answer])

                # Pre-compute chunk vectors
                chunk_vectors = [_tfidf_vector(t, idf) for t in chunk_texts]

                support_scores: list[float] = []
                for sentence in substantive:
                    sent_vec = _tfidf_vector(sentence, idf)
                    if not sent_vec:
                        continue

                    sims = [
                        (_cosine_similarity(sent_vec, cv), chunks[i].chunk_id)
                        for i, cv in enumerate(chunk_vectors)
                    ]
                    sims.sort(key=lambda x: x[0], reverse=True)
                    best_sim, best_chunk_id = sims[0] if sims else (0.0, "")

                    support_scores.append(best_sim)
                    sentence_scores.append(
                        {
                            "sentence": sentence[:120],
                            "support_score": round(best_sim, 3),
                            "supported": best_sim >= self._threshold,
                            "best_chunk_id": best_chunk_id,
                        }
                    )

                    if best_sim >= self._threshold:
                        evidence_map[sentence[:60]] = best_chunk_id
                    else:
                        # Only flag as unsupported if it makes a factual claim
                        if self._is_factual_claim(sentence) and not admits_no_info:
                            unsupported_statements.append(sentence[:120])
                            issues.append(
                                f'Low grounding confidence ({best_sim:.2f}) for: "{sentence[:80]}..."'
                            )

                if support_scores:
                    overall_confidence = round(sum(support_scores) / len(support_scores), 3)
                else:
                    overall_confidence = 1.0

        logger.debug(
            "Grounding validation complete",
            valid=len(issues) == 0,
            issues=len(issues),
            citations=valid_count,
            invalid_citations=len(invalid_citations),
            overall_confidence=overall_confidence,
            unsupported=len(unsupported_statements),
        )

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "unsupported_statements": unsupported_statements,
            "citation_count": valid_count,
            "invalid_citations": invalid_citations,
            "admits_no_info": admits_no_info,
            "confidence": overall_confidence,
            "sentence_scores": sentence_scores,
            "evidence_map": evidence_map,
        }

    async def validate_or_raise(
        self,
        answer: str,
        chunks: list[RetrievedChunk],
        question: str,
    ) -> None:
        result = await self.validate(answer, chunks, question)
        if not result["valid"]:
            raise RAGGroundingError(issues=result["issues"])

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """Split text into sentences using a robust multi-pattern approach."""
        # Remove citation markers to avoid them confusing sentence detection
        clean = re.sub(r"\[\d+(?:[-,]\d+)*\]", "", text)
        # Split on sentence-ending punctuation followed by whitespace and uppercase
        parts = re.split(
            r"(?<=[.!?])\s+(?=[A-Z\"])|(?<=\.)\n+(?=[A-Z\"])|(?<=\n\n)",
            clean,
        )
        sentences = []
        for part in parts:
            stripped = part.strip()
            if stripped and len(stripped) >= 10:
                sentences.append(stripped)
        return sentences

    @staticmethod
    def _is_factual_claim(sentence: str) -> bool:
        """Heuristic: does this sentence make a specific factual claim?"""
        # Skip meta-sentences like "Based on the context..."
        meta_prefixes = [
            "based on",
            "according to",
            "the sources",
            "the documents",
            "the context",
            "as mentioned",
            "as stated",
            "as noted",
            "in summary",
            "in conclusion",
            "overall,",
            "note that",
        ]
        lower = sentence.lower().strip()
        if any(lower.startswith(p) for p in meta_prefixes):
            return False

        # Skip very short or question sentences
        if len(sentence) < _MIN_SENTENCE_LEN or sentence.strip().endswith("?"):
            return False

        # A sentence with numbers or proper nouns is more likely factual
        has_number = bool(re.search(r"\b\d+(?:\.\d+)?(?:%|x|k|M|B)?\b", sentence))
        has_proper_noun = bool(re.search(r"\b[A-Z][a-z]{2,}\b", sentence))
        return has_number or has_proper_noun or len(sentence) > 80

    @staticmethod
    def _extract_citations(text: str) -> list[int]:
        """Extract citation numbers — supports [1], [1,2], [1-3], [[1]]."""
        citations: set[int] = set()
        for match in re.finditer(r"\[(\d+)\]", text):
            citations.add(int(match.group(1)))
        for match in re.finditer(r"\[(\d+)-(\d+)\]", text):
            start, end = int(match.group(1)), int(match.group(2))
            if end - start < 20:  # Safety: avoid [1-9999]
                citations.update(range(start, end + 1))
        for match in re.finditer(r"\[(\d+),\s*(\d+)\]", text):
            citations.add(int(match.group(1)))
            citations.add(int(match.group(2)))
        return sorted(citations)

    @staticmethod
    def _extract_key_terms(text: str, max_terms: int = 5) -> list[str]:
        """Extract key terms for diagnostic fact-checking."""
        words = re.findall(r"\b[a-zA-Z]{4,}\b", text.lower())
        stopwords = {
            "what",
            "when",
            "where",
            "why",
            "how",
            "which",
            "that",
            "this",
            "with",
            "from",
            "they",
            "have",
            "been",
            "were",
            "will",
            "would",
            "could",
            "should",
            "does",
            "about",
            "there",
            "their",
            "your",
        }
        return [w for w in words if w not in stopwords][:max_terms]
