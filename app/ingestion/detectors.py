"""Language and content detection module.

All synchronous calls offloaded via ``run_in_executor``.
"""

from app.core.logging import get_logger
from app.ingestion.executor import run_in_executor

logger = get_logger(__name__)


class LanguageDetector:
    """Detects document language from text content."""

    SUPPORTED_LANGUAGES = {
        "af": "Afrikaans", "ar": "Arabic", "bg": "Bulgarian",
        "bn": "Bengali", "ca": "Catalan", "cs": "Czech",
        "da": "Danish", "de": "German", "el": "Greek",
        "en": "English", "es": "Spanish", "et": "Estonian",
        "fa": "Persian", "fi": "Finnish", "fr": "French",
        "gu": "Gujarati", "he": "Hebrew", "hi": "Hindi",
        "hr": "Croatian", "hu": "Hungarian", "id": "Indonesian",
        "it": "Italian", "ja": "Japanese", "kn": "Kannada",
        "ko": "Korean", "lt": "Lithuanian", "lv": "Latvian",
        "mk": "Macedonian", "ml": "Malayalam", "mr": "Marathi",
        "ne": "Nepali", "nl": "Dutch", "no": "Norwegian",
        "pa": "Punjabi", "pl": "Polish", "pt": "Portuguese",
        "ro": "Romanian", "ru": "Russian", "sk": "Slovak",
        "sl": "Slovenian", "so": "Somali", "sq": "Albanian",
        "sr": "Serbian", "sv": "Swedish", "sw": "Swahili",
        "ta": "Tamil", "te": "Telugu", "th": "Thai",
        "tl": "Filipino", "tr": "Turkish", "uk": "Ukrainian",
        "ur": "Urdu", "vi": "Vietnamese", "zh-cn": "Chinese (Simplified)",
        "zh-tw": "Chinese (Traditional)", "zh": "Chinese",
    }

    def __init__(self, min_text_length: int = 20) -> None:
        self.min_text_length = min_text_length

    async def detect(self, text: str) -> tuple[str, float]:
        """Detect language, offloaded to executor."""
        if not text or len(text.strip()) < self.min_text_length:
            return "en", 0.5

        def _do() -> tuple[str, float]:
            from langdetect import detect_langs
            detections = detect_langs(text)
            if detections:
                best = detections[0]
                return best.lang, round(best.prob, 4)
            return "en", 0.5

        try:
            return await run_in_executor(_do)
        except Exception as e:
            logger.debug("Language detection failed", error=str(e))
            return "en", 0.5

    async def detect_multilingual(
        self, text: str, min_segment_length: int = 50
    ) -> dict[str, float]:
        """Detect multilingual content, offloaded to executor."""
        if not text or len(text.strip()) < self.min_text_length:
            return {"en": 1.0}

        def _do() -> dict[str, float]:
            from langdetect import detect
            segments = [p.strip() for p in text.split("\n") if len(p.strip()) >= min_segment_length]
            if not segments:
                return {"en": 1.0}
            lang_counts: dict[str, int] = {}
            for segment in segments:
                try:
                    lang = detect(segment)
                    lang_counts[lang] = lang_counts.get(lang, 0) + 1
                except Exception:
                    continue
            if not lang_counts:
                return {"en": 1.0}
            total = sum(lang_counts.values())
            return {lang: round(count / total, 4) for lang, count in sorted(lang_counts.items(), key=lambda x: x[1], reverse=True)}

        try:
            return await run_in_executor(_do)
        except Exception as e:
            logger.debug("Multilingual detection failed", error=str(e))
            return {"en": 1.0}

    def language_name(self, code: str) -> str:
        return self.SUPPORTED_LANGUAGES.get(code, code)

    async def is_supported(self, code: str) -> bool:
        return code in self.SUPPORTED_LANGUAGES


language_detector = LanguageDetector()
