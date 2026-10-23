import re
import unicodedata
from typing import Dict, Any

# Map decomposed Devanagari base + nukta -> precomposed single codepoint
DEVANAGARI_NUKTA_MAP = {
    "\u0915\u093C": "\u0958",  # क़
    "\u0916\u093C": "\u0959",  # ख़
    "\u0917\u093C": "\u095A",  # ग़
    "\u091C\u093C": "\u095B",  # ज़
    "\u0921\u093C": "\u095C",  # ड़
    "\u0922\u093C": "\u095D",  # ढ़
    "\u092B\u093C": "\u095E",  # फ़
    "\u092F\u093C": "\u095F",  # य़
}

# Invisible Unicode characters: Zero-Width Space, ZWNJ, ZWJ, LTR/RTL marks, Soft Hyphen, BOM
INVISIBLE_CHARS_REGEX = re.compile(
    r"[\u200B\u200C\u200D\u200E\u200F\uFEFF\u00AD\u2060\u180E]"
)

WHITESPACE_REGEX = re.compile(r"[^\S\r\n]+")
MULTILINE_BREAKS_REGEX = re.compile(r"\n{3,}")


def normalize_unicode(text: str) -> str:
    """
    Applies Unicode NFC normalization, unifies Devanagari Nuktas,
    removes invisible characters, and normalizes whitespace.
    """
    if not text:
        return ""

    # 1. Unicode NFC normalization
    text = unicodedata.normalize("NFC", text)

    # 2. Devanagari Nukta canonicalization
    for decomposed, precomposed in DEVANAGARI_NUKTA_MAP.items():
        text = text.replace(decomposed, precomposed)

    # 3. Strip invisible characters
    text = INVISIBLE_CHARS_REGEX.sub("", text)

    # 4. Standardize Devanagari Purna Viram 
    text = re.sub(r"(?<=[\u0900-\u097F])\s*\|\s*", "। ", text)

    # 5. Whitespace normalization
    text = text.replace("\u00A0", " ")
    text = WHITESPACE_REGEX.sub(" ", text)
    text = MULTILINE_BREAKS_REGEX.sub("\n\n", text)

    return text.strip()


def normalize_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Pipeline step wrapper: normalizes doc['text'] in place.
    """
    doc["text"] = normalize_unicode(doc.get("text", ""))
    return doc
