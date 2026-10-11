"""Email the recruiters when a visitor applies on the careers page.

Sent over SMTP with STARTTLS (Google Workspace by default). A failure is logged and never
reaches the visitor; the application is already saved when this runs.
"""

from dataclasses import dataclass
from email.message import EmailMessage
from html import escape
import logging
import smtplib

from app.config import Settings, get_settings

logger = logging.getLogger("talent")


@dataclass
class ApplicationNotice:
    submission_id: str
    created: bool
    requisition_code: str
    title: str | None
    job_location: str | None
    full_name: str
    email: str
    phone: str
    location: str
    salary_usd: int
    start_on: str
    years_experience: int
    last_tssci_on: str | None
    last_fsp_on: str | None
    note: str | None


def recipients(settings: Settings) -> list[str]:
    return [item.strip() for item in settings.notify_to.split(",") if item.strip()]


def enabled(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return bool(recipients(settings) and settings.smtp_host and settings.smtp_username and settings.smtp_password)


def build_message(notice: ApplicationNotice, settings: Settings) -> EmailMessage:
    base = (settings.desk_url or settings.public_base_url).rstrip("/")
    link = f"{base}/admin/submissions/{notice.submission_id}"
    role = f"{notice.requisition_code} {notice.title or 'Open role'}"
    verb = "New application" if notice.created else "Updated application"
    rows = [
        ("Job", f"{role}" + (f" · {notice.job_location}" if notice.job_location else "")),
        ("Name", notice.full_name),
        ("Email", notice.email),
        ("Phone", notice.phone),
        ("Lives in", notice.location),
        ("Desired salary", f"${notice.salary_usd:,}"),
        ("Can start", notice.start_on),
        ("Experience", f"{notice.years_experience} years"),
        ("Clearance", "Attested TS/SCI with Full Scope Polygraph"),
    ]
    if notice.last_tssci_on:
        rows.append(("Last TS/SCI", notice.last_tssci_on))
    if notice.last_fsp_on:
        rows.append(("Last FSP", notice.last_fsp_on))
    if notice.note:
        rows.append(("Note", notice.note))

    message = EmailMessage()
    message["Subject"] = f"{verb}: {notice.full_name} for {role}"
    message["From"] = settings.notify_from or settings.smtp_username
    message["To"] = ", ".join(recipients(settings))
    message["Reply-To"] = notice.email
    text = "\n".join(f"{label}: {value}" for label, value in rows)
    message.set_content(f"{verb} on the careers site.\n\n{text}\n\nOpen in the desk: {link}\n")
    cells = "".join(
        f'<tr><td style="padding:4px 16px 4px 0;color:#6b6760;white-space:nowrap;vertical-align:top">{escape(label)}</td>'
        f'<td style="padding:4px 0;color:#151413">{escape(value)}</td></tr>'
        for label, value in rows
    )
    message.add_alternative(
        f"""<div style="font-family:-apple-system,Segoe UI,Arial,sans-serif;font-size:14px;line-height:1.5">
<p style="margin:0 0 12px">{escape(verb)} on the careers site.</p>
<table style="border-collapse:collapse">{cells}</table>
<p style="margin:20px 0 0"><a href="{escape(link)}" style="background:#151413;color:#fff;padding:10px 16px;border-radius:999px;text-decoration:none">Open in the desk</a></p>
<p style="margin:16px 0 0;color:#8a857d;font-size:12px">The résumé is in the desk. Reply to this email to write to the candidate.</p>
</div>""",
        subtype="html",
    )
    return message


def send_application_notice(notice: ApplicationNotice) -> bool:
    settings = get_settings()
    if not enabled(settings):
        return False
    try:
        message = build_message(notice, settings)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
        return True
    except Exception as exc:  # noqa: BLE001 - the application is saved; email is best effort.
        logger.warning("application email for %s failed: %s", notice.requisition_code, exc)
        return False


if __name__ == "__main__":
    import sys

    current = get_settings()
    if not enabled(current):
        sys.exit("Email is off. Set NOTIFY_TO, SMTP_USERNAME, and SMTP_PASSWORD in .env.")
    sample = ApplicationNotice(
        submission_id="00000000-0000-0000-0000-000000000000",
        created=True,
        requisition_code="TEST",
        title="Sample role (test email)",
        job_location="McLean, VA",
        full_name="Test Applicant",
        email=current.smtp_username,
        phone="703-555-0100",
        location="Chantilly, VA",
        salary_usd=150000,
        start_on="2026-11-01",
        years_experience=8,
        last_tssci_on=None,
        last_fsp_on=None,
        note="This is a test of the application email.",
    )
    sys.exit(0 if send_application_notice(sample) else "Sending failed. The API log line above has the reason.")
