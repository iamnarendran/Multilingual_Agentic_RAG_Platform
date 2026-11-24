"""Language detection tuned for English + Indian languages.

Strategy: count characters per Unicode *script* first (deterministic and very reliable for
Indic scripts), then use langdetect only to disambiguate languages that share a script
(e.g. Hindi / Marathi / Nepali on Devanagari) or for Latin-script text.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from langdetect import DetectorFactory, LangDetectException, detect_langs

DetectorFactory.seed = 0  # make langdetect deterministic

LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "hi": "Hindi",
    "bn": "Bengali",
    "te": "Telugu",
    "mr": "Marathi",
    "ta": "Tamil",
    "ur": "Urdu",
    "gu": "Gujarati",
    "kn": "Kannada",
    "ml": "Malayalam",
    "or": "Odia",
    "pa": "Punjabi",
    "as": "Assamese",
    "mai": "Maithili",
    "sa": "Sanskrit",
    "ks": "Kashmiri",
    "ne": "Nepali",
    "sd": "Sindhi",
    "kok": "Konkani",
    "doi": "Dogri",
    "mni": "Manipuri",
    "sat": "Santali",
    "brx": "Bodo",
    # Common non-Indian languages the LLM can still answer in
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "pt": "Portuguese",
    "it": "Italian",
    "ar": "Arabic",
    "fa": "Persian",
    "zh-cn": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "ru": "Russian",
    "id": "Indonesian",
}

# (start, end, script)
_SCRIPT_RANGES: list[tuple[int, int, str]] = [
    (0x0900, 0x097F, "devanagari"),
    (0x0980, 0x09FF, "bengali"),
    (0x0A00, 0x0A7F, "gurmukhi"),
    (0x0A80, 0x0AFF, "gujarati"),
    (0x0B00, 0x0B7F, "oriya"),
    (0x0B80, 0x0BFF, "tamil"),
    (0x0C00, 0x0C7F, "telugu"),
    (0x0C80, 0x0CFF, "kannada"),
    (0x0D00, 0x0D7F, "malayalam"),
    (0x0600, 0x06FF, "arabic"),
    (0x0750, 0x077F, "arabic"),
    (0x1C50, 0x1C7F, "olchiki"),
    (0xABC0, 0xABFF, "meetei"),
    (0x4E00, 0x9FFF, "cjk"),
    (0x0400, 0x04FF, "cyrillic"),
]

# Scripts used by exactly one of our languages
_UNIQUE_SCRIPT_LANG = {
    "gurmukhi": "pa",
    "gujarati": "gu",
    "oriya": "or",
    "tamil": "ta",
    "telugu": "te",
    "kannada": "kn",
    "malayalam": "ml",
    "olchiki": "sat",
    "meetei": "mni",
    "bengali": "bn",
}

# Tesseract traineddata names per script (used to pick OCR languages)
SCRIPT_TO_TESSERACT = {
    "devanagari": ["hin", "mar", "nep", "san"],
    "bengali": ["ben", "asm"],
    "gurmukhi": ["pan"],
    "gujarati": ["guj"],
    "oriya": ["ori"],
    "tamil": ["tam"],
    "telugu": ["tel"],
    "kannada": ["kan"],
    "malayalam": ["mal"],
    "arabic": ["urd", "ara"],
    "latin": ["eng"],
}


@dataclass(frozen=True)
class DetectedLanguage:
    code: str
    name: str
    script: str
    confidence: float


def _script_of(ch: str) -> str | None:
    cp = ord(ch)
    if ("a" <= ch <= "z") or ("A" <= ch <= "Z") or 0x00C0 <= cp <= 0x024F:
        return "latin"
    for start, end, script in _SCRIPT_RANGES:
        if start <= cp <= end:
            return script
    return None


def script_counts(text: str) -> Counter[str]:
    return Counter(s for s in map(_script_of, text) if s)


def dominant_script(text: str) -> tuple[str, float]:
    counts = script_counts(text)
    total = sum(counts.values())
    if not total:
        return "unknown", 0.0
    script, n = counts.most_common(1)[0]
    return script, n / total


def _langdetect(text: str, allowed: set[str] | None = None) -> tuple[str, float] | None:
    try:
        candidates = detect_langs(text)
    except LangDetectException:
        return None
    for cand in candidates:
        if allowed is None or cand.lang in allowed:
            return cand.lang, float(cand.prob)
    return None


def detect_language(text: str) -> DetectedLanguage:
    sample = text[:2000]
    script, share = dominant_script(sample)

    if script in _UNIQUE_SCRIPT_LANG:
        code = _UNIQUE_SCRIPT_LANG[script]
        return DetectedLanguage(code, LANGUAGE_NAMES[code], script, round(min(1.0, 0.5 + share / 2), 3))

    if script == "devanagari":
        found = _langdetect(sample, {"hi", "mr", "ne"})
        code, conf = found if found else ("hi", 0.6)
        return DetectedLanguage(code, LANGUAGE_NAMES[code], script, round(conf * share, 3))

    if script == "arabic":
        found = _langdetect(sample, {"ur", "ar", "fa"})
        code, conf = found if found else ("ur", 0.6)
        return DetectedLanguage(code, LANGUAGE_NAMES.get(code, code), script, round(conf * share, 3))

    if script == "latin":
        # Very short Latin strings ("hi", "ok thanks") are unreliable for langdetect.
        if len(sample.split()) < 3:
            return DetectedLanguage("en", "English", script, 0.5)
        found = _langdetect(sample)
        code, conf = found if found else ("en", 0.5)
        return DetectedLanguage(code, LANGUAGE_NAMES.get(code, code), script, round(conf * share, 3))

    found = _langdetect(sample) if script != "unknown" else None
    if found:
        code, conf = found
        return DetectedLanguage(code, LANGUAGE_NAMES.get(code, code), script, round(conf, 3))
    return DetectedLanguage("en", "English", script, 0.0)


def language_name(code: str | None) -> str:
    if not code:
        return "Unknown"
    return LANGUAGE_NAMES.get(code, code)
