import re
from typing import Dict, Any

# 1. Email Regex (Standard RFC compliant)
EMAIL_REGEX = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

# 2. Indian PAN Card Regex (5 uppercase letters, 4 digits, 1 uppercase letter)
PAN_REGEX = re.compile(
    r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"
)

# 3. Aadhaar Regex (12 digits, does not start with 0 or 1, optional spaces/hyphens)
# Evaluated BEFORE phone regex so 12-digit Aadhaar is not partially matched as a 10-digit phone
AADHAAR_REGEX = re.compile(
    r"\b[2-9]\d{3}[\s-]?\d{4}[\s-]?\d{4}\b"
)

# 4. Indian Mobile Number Regex (10 digits starting with 6, 7, 8, 9 with optional +91/0 prefix)
PHONE_REGEX = re.compile(
    r"(?:(?:\+91|91|0)[\s-]?)?[6-9]\d{4}[\s-]?\d{5}\b"
)


def redact_pii(text: str) -> str:
    """
    Redacts Indian PII from text, replacing matches with:
    <EMAIL>, <PAN>, <AADHAAR>, <PHONE>.
    Non-PII numbers (years, pincodes, populations, stats) survive untouched.
    """
    if not text:
        return ""

    # Replace Email
    text = EMAIL_REGEX.sub("<EMAIL>", text)

    # Replace PAN Card
    text = PAN_REGEX.sub("<PAN>", text)

    # Replace Aadhaar (12 digits) before Phone (10 digits) to avoid prefix collision
    text = AADHAAR_REGEX.sub("<AADHAAR>", text)

    # Replace Indian Phone numbers
    text = PHONE_REGEX.sub("<PHONE>", text)

    return text


def redact_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Pipeline step wrapper: redacts PII in doc['text'] in place.
    """
    doc["text"] = redact_pii(doc.get("text", ""))
    return doc
