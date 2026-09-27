"""Social Security number redaction. Runs before storage, logs, LLM, and embeddings."""

import re

_DASHED = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_LABELED = re.compile(
    r"(?i)\b(?:ssn|social\s+security(?:\s+(?:number|no\.?))?)[\s:#\-]*"
    r"(\d{3}[-\s]?\d{2}[-\s]?\d{4}|\d{9})\b"
)
_BEFORE_LABEL = re.compile(
    r"(?i)\b(\d{3}[-\s]?\d{2}[-\s]?\d{4}|\d{9})\b(?=\s*\(?\s*(?:ssn|social\s+security)\b)"
)


def redact_ssn(text: str) -> str:
    if not text:
        return text

    def _labeled(match: re.Match[str]) -> str:
        return match.group(0).replace(match.group(1), "[REDACTED]")

    text = _LABELED.sub(_labeled, text)
    text = _BEFORE_LABEL.sub("[REDACTED]", text)
    text = _DASHED.sub("[REDACTED]", text)
    return text


def contains_ssn(text: str) -> bool:
    if not text:
        return False
    if _DASHED.search(text):
        return True
    if re.search(r"(?i)\b(?:ssn|social\s+security)\b.{0,20}\d{9}\b", text):
        return True
    if re.search(r"\b\d{9}\b.{0,12}\bSSN\b", text, re.I):
        return True
    return False
