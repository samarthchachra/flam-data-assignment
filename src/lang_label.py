
import re
from typing import Dict, Any

# Devanagari Unicode Block: \u0900 - \u097F
DEV_REGEX = re.compile(r"[\u0900-\u097F]")
LATIN_REGEX = re.compile(r"[a-zA-Z]")
WORD_REGEX = re.compile(r"[a-zA-Z]+")

# High-frequency Hindi grammatical markers in Latin script
HINGLISH_MARKERS = {
    "hai", "hain", "karo", "kare", "karen", "karna", "kardo",
    "kya", "kyu", "kyun", "nahi", "nahin", "mera", "meri", "mere",
    "mujhe", "muje", "hum", "tum", "aap", "liye", "hoga", "hogi",
    "hoge", "bhi", "toh", "mai", "main", "aaj", "kal", "par",
    "aur", "kaunsa", "raha", "rahe", "rahi", "wala", "wali", "wale",
    "ko", "se", "ka", "ki", "ke", "me", "mein", "pe", "ab", "tha",
    "thi", "the", "batao", "dikhao", "chahiye", "karoge", "karta"
}

def identify_language(text: str) -> str:
    """
    Labels text with exactly one of: 'hi', 'hi-Latn', 'en or other'.
    Uses character distribution and grammatical marker lookup.
    """
    if not text or not text.strip():
        return "en or other"

    dev_chars = len(DEV_REGEX.findall(text))
    latin_chars = len(LATIN_REGEX.findall(text))
    total_alpha = dev_chars + latin_chars

    if total_alpha == 0:
        return "en or other"

    # 1. Hindi in Devanagari (including Devanagari with English words mixed in)
    if (dev_chars / total_alpha) >= 0.30 or (dev_chars >= 10 and dev_chars > latin_chars):
        return "hi"

    # 2. Hindi written in Latin script (Hinglish)
    words = [w.lower() for w in WORD_REGEX.findall(text)]
    if words and latin_chars > dev_chars:
        matched_markers = {w for w in words if w in HINGLISH_MARKERS}
        # Classified as hi-Latn if at least 2 distinct markers exist or >= 10% of tokens match
        if len(matched_markers) >= 2 or (len(words) >= 3 and len(matched_markers) / len(words) >= 0.10):
            return "hi-Latn"

    # 3. Pure English or other languages
    return "en or other"

def label_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Pipeline step wrapper: attaches 'lang' key to document.
    """
    doc["lang"] = identify_language(doc.get("text", ""))
    return doc
