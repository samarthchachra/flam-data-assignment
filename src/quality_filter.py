import re
from typing import Tuple, Optional, Dict, Any

# 1. Markup & Link Regexes
HTML_TAGS_REGEX = re.compile(r"<[^>]+>", re.DOTALL)
WIKI_TEMPLATE_REGEX = re.compile(r"\{\{.*?\}\}", re.DOTALL)
WIKI_LINK_PIPED_REGEX = re.compile(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]")
WIKI_HEADER_REGEX = re.compile(r"={2,}\s*(.*?)\s*={2,}")
URL_REGEX = re.compile(r"https?://\S+|www\.\S+")

# 2. Noise & Repetition Regexes
REPEATED_CHARS_REGEX = re.compile(r"(.)\1{3,}")          # 'aaaaa' -> 'aa'
REPEATED_PUNCT_REGEX = re.compile(r"([!?.,;:])\1{2,}")  # '?????' -> '?'
MOJIBAKE_MAP = {
    "â€™": "'", "â€œ": '"', "â€\x9d": '"', "â€”": "—", "â€“": "–",
    "\ufffd": " "
}

# 3. Known boilerplate lines (common navigation/legal headers)
BOILERPLATE_PATTERNS = [
    re.compile(r"^\s*(इन्हें भी देखें|बाहरी कड़ियाँ|संदर्भ|स्रोत|टिप्पणी)\s*$", re.IGNORECASE),
    re.compile(r"^\s*(see also|external links|references|notes|further reading)\s*$", re.IGNORECASE),
    re.compile(r"^\s*(all rights reserved|terms of service|privacy policy)\s*$", re.IGNORECASE)
]


def clean_markup_and_noise(text: str) -> str:
    """
    Strips markup, URLs, boilerplate lines, and collapses repetition spam.
    """
    if not text:
        return ""

    for bad, good in MOJIBAKE_MAP.items():
        text = text.replace(bad, good)

    text = WIKI_TEMPLATE_REGEX.sub("", text)
    text = HTML_TAGS_REGEX.sub("", text)
    text = WIKI_LINK_PIPED_REGEX.sub(r"\1", text)
    text = WIKI_HEADER_REGEX.sub(r"\1", text)
    text = URL_REGEX.sub("", text)

    cleaned_lines = []
    for line in text.split("\n"):
        if any(bp.match(line) for bp in BOILERPLATE_PATTERNS):
            continue
        cleaned_lines.append(line)
    text = "\n".join(cleaned_lines)

    text = REPEATED_CHARS_REGEX.sub(r"\1\1", text)
    text = REPEATED_PUNCT_REGEX.sub(r"\1", text)

    return text.strip()


def evaluate_quality(text: str) -> Tuple[bool, str]:
    """
    Evaluates document quality using structural properties.
    Returns (True, '') if kept, or (False, drop_reason) if dropped.
    """
    if not text or len(text.strip()) == 0:
        return False, "empty_after_cleaning"

    words = text.split()
    total_chars = len(text)

    # 1. Minimum length constraint
    if len(words) < 3 or total_chars < 15:
        return False, "too_short_fragment"

    # 2. Excessive symbols check (punctuation ratio > 40%)
    non_space = [c for c in text if not c.isspace()]
    if non_space:
        symbol_count = sum(1 for c in non_space if not c.isalnum() and c not in "।,?!.:;'\")(-")
        if (symbol_count / len(non_space)) > 0.40:
            return False, "excessive_symbols"

    # 3. Mostly numeric junk (> 70% digits)
    digit_count = sum(1 for c in text if c.isdigit())
    if (digit_count / total_chars) > 0.70:
        return False, "mostly_numeric_junk"

    # 4. Repetitive single-word spam (e.g. 'test test test test')
    if len(words) >= 4 and len(set(words)) == 1:
        return False, "repetitive_word_spam"

    return True, ""


def filter_document(doc: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, str]]]:
    """
    Pipeline step wrapper:
    Returns (cleaned_doc, None) if kept, or (None, drop_record) if dropped.
    """
    cleaned_text = clean_markup_and_noise(doc.get("text", ""))
    is_valid, reason = evaluate_quality(cleaned_text)

    if is_valid:
        doc["text"] = cleaned_text
        return doc, None

    drop_record = {
        "id": doc.get("id", "unknown"),
        "status": "dropped",
        "stage": "quality_filter",
        "reason": reason,
        "dup_of": ""
    }
    return None, drop_record
