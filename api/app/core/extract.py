"""Résumé and description text extraction. Clearance wording is never a rejection."""

from io import BytesIO
from pathlib import Path
import shutil
import subprocess
import tempfile

from docx import Document
from pypdf import PdfReader
from pypdf.errors import PdfReadError


class ExtractError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


_ALLOWED = {".pdf", ".docx", ".doc", ".txt"}
_IMAGES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".tif", ".tiff", ".bmp"}
_MAX_BYTES = 10 * 1024 * 1024


def extract_text(filename: str, data: bytes) -> str:
    name = (filename or "").lower().strip()
    suffix = "." + name.rsplit(".", 1)[-1] if "." in name else ""
    if len(data) > _MAX_BYTES:
        raise ExtractError("File is larger than 10 MB.")
    if suffix in _IMAGES:
        raise ExtractError("This looks like an image. Upload a text-based PDF, DOC, DOCX, or TXT file.")
    if suffix not in _ALLOWED:
        raise ExtractError("Upload a PDF, DOC, DOCX, or TXT file.")
    if suffix == ".txt":
        text = data.decode("utf-8", errors="replace")
    elif suffix == ".docx":
        text = _docx(data)
    elif suffix == ".doc":
        text = _doc(data)
    else:
        text = _pdf(data)
    if len(text.strip()) < 200:
        raise ExtractError("This file needs a text-based export. Almost no text could be read.")
    return text


def _doc(data: bytes) -> str:
    """Word 97–2003 .doc. A file that is really a DOCX is read as DOCX."""
    if data[:2] == b"PK":
        return _docx(data)
    if not data.startswith(b"\xd0\xcf\x11\xe0"):
        raise ExtractError("Could not read that Word .doc file.")
    text = _antiword(data) or _soffice_text(data)
    if len(text.strip()) < 200:
        raise ExtractError("Could not read that Word .doc file.")
    return text


def _antiword(data: bytes) -> str:
    if shutil.which("antiword") is None:
        return ""
    return _convert(data, ["antiword", "-m", "UTF-8.txt"], timeout=30)


def _soffice_text(data: bytes) -> str:
    if shutil.which("soffice") is None:
        return ""
    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder) / "resume.doc"
        source.write_bytes(data)
        try:
            subprocess.run(
                ["soffice", "--headless", "--convert-to", "txt:Text", "--outdir", folder, str(source)],
                capture_output=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        written = Path(folder) / "resume.txt"
        if not written.is_file():
            return ""
        return written.read_text(encoding="utf-8", errors="replace")


def _convert(data: bytes, command: list[str], *, timeout: int) -> str:
    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder) / "resume.doc"
        source.write_bytes(data)
        try:
            done = subprocess.run(
                [*command, str(source)],
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
    return done.stdout.decode("utf-8", errors="replace")


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
