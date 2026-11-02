"""A résumé download that keeps the original text and adds the recruiter's justifications."""

from datetime import date
from io import BytesIO

from docx import Document


MIN_JUSTIFICATION = 20
MAX_JUSTIFICATION = 2000


def clean_justification(text: str) -> str:
    """Collapse whitespace. Empty stays empty so a draft can omit a line."""
    return " ".join((text or "").split())


def justification_error(text: str) -> str | None:
    if not text:
        return None
    if len(text) < MIN_JUSTIFICATION:
        return "Write a full sentence for each missing requirement."
    if len(text) > MAX_JUSTIFICATION:
        return "Keep each justification under 2,000 characters."
    return None


def build_updated_resume(
    *,
    name: str,
    code: str,
    title: str | None,
    filename: str | None,
    author: str,
    items: list[dict],
    resume_text: str,
    today: date | None = None,
) -> bytes:
    """DOCX the desk can hand to a client. The uploaded file is not modified."""
    today = today or date.today()
    document = Document()
    document.add_heading(name or "Résumé", 0)
    intro = document.add_paragraph()
    intro.add_run(f"Updated for {code}")
    if title:
        intro.add_run(f" · {title}")
    document.add_paragraph(f"Requirement notes written by {author or 'the desk'} on {today.isoformat()}.")
    if filename:
        document.add_paragraph(f"Original file on the desk: {filename}. That file is unchanged.")

    document.add_heading("Requirement justifications", 1)
    document.add_paragraph("These notes address requirements the résumé does not already show.")
    for item in items:
        label = document.add_paragraph()
        kind = item.get("kind") or "Requirement"
        label.add_run(f"{kind}. ").italic = True
        label.add_run(item.get("line") or "").bold = True
        document.add_paragraph(item.get("justification") or "")

    document.add_heading("Résumé", 1)
    body = (resume_text or "").strip()
    if not body:
        document.add_paragraph("The résumé text is not on file.")
    else:
        for line in body.splitlines():
            document.add_paragraph(line)

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def download_name(name: str, code: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in " .-_" else " " for ch in (name or "resume"))
    safe = " ".join(safe.split()) or "resume"
    return f"{safe} - {code} - updated.docx"
