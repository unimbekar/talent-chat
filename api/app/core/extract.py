"""Résumé and description text extraction. Clearance wording is never a rejection."""

from io import BytesIO

from docx import Document
from pypdf import PdfReader
from pypdf.errors import PdfReadError


class ExtractError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


_ALLOWED = {".pdf", ".docx", ".txt"}
_IMAGES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".tif", ".tiff", ".bmp"}
_MAX_BYTES = 10 * 1024 * 1024


def extract_text(filename: str, data: bytes) -> str:
    name = (filename or "").lower().strip()
    suffix = "." + name.rsplit(".", 1)[-1] if "." in name else ""
    if len(data) > _MAX_BYTES:
        raise ExtractError("File is larger than 10 MB.")
    if suffix == ".doc":
        raise ExtractError("Save as DOCX or PDF and upload again")
    if suffix in _IMAGES:
        raise ExtractError("This looks like an image. Upload a text-based PDF, DOCX, or TXT file.")
    if suffix not in _ALLOWED:
        raise ExtractError("Upload a PDF, DOCX, or TXT file.")
    if suffix == ".txt":
        text = data.decode("utf-8", errors="replace")
    elif suffix == ".docx":
        text = _docx(data)
    else:
        text = _pdf(data)
    if len(text.strip()) < 200:
        raise ExtractError("This file needs a text-based export. Almost no text could be read.")
    return text


def _docx(data: bytes) -> str:
    try:
        document = Document(BytesIO(data))
    except Exception as exc:
        raise ExtractError("Could not read that DOCX file.") from exc
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def _pdf(data: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(data))
    except PdfReadError as exc:
        raise ExtractError("Could not read that PDF.") from exc
    if reader.is_encrypted:
        try:
            opened = reader.decrypt("")
        except Exception as exc:
            raise ExtractError("This PDF is password-protected. Remove the password and upload again.") from exc
        if opened == 0:
            raise ExtractError("This PDF is password-protected. Remove the password and upload again.")
    try:
        parts = [(page.extract_text() or "") for page in reader.pages]
    except PdfReadError as exc:
        raise ExtractError("This PDF is password-protected. Remove the password and upload again.") from exc
    return "\n".join(parts)
