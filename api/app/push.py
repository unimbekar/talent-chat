"""Phone and desktop push notifications for the installed recruiter desk.

Standard Web Push: no account, password, or paid service. The server signs each message with
its own VAPID key, made on first use and kept in push_keys. Payloads are encrypted for the
device, so the browser's push service (Google, Apple, Mozilla) cannot read them.
"""

from base64 import urlsafe_b64encode
from datetime import datetime, timezone
import json
import logging
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid02
from pywebpush import WebPushException, webpush
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import PushKey, PushSubscription

logger = logging.getLogger("talent")

# Subscriptions may only point at the browsers' push services, never at an arbitrary host.
PUSH_HOSTS = (
    "fcm.googleapis.com",
    "android.googleapis.com",
    ".push.apple.com",
    "updates.push.services.mozilla.com",
    ".notify.windows.com",
)


def allowed_endpoint(endpoint: str) -> bool:
    parts = urlsplit(endpoint)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host:
        return False
    return any(host == item or (item.startswith(".") and host.endswith(item)) for item in PUSH_HOSTS)


def _public_key(vapid: Vapid02) -> str:
    raw = vapid.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return urlsafe_b64encode(raw).decode().rstrip("=")


def vapid_key(session: Session) -> tuple[Vapid02, str]:
    row = session.get(PushKey, 1)
    if row is None:
        vapid = Vapid02()
        vapid.generate_keys()
        row = PushKey(id=1, private_pem=vapid.private_pem().decode(), public_key=_public_key(vapid))
        session.add(row)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            row = session.get(PushKey, 1)
    assert row is not None
    return Vapid02.from_pem(row.private_pem.encode()), row.public_key


def _subject() -> str:
    settings = get_settings()
    sender = settings.notify_from or settings.smtp_username
    if "<" in sender:
        sender = sender.split("<", 1)[1].rstrip(">")
    return f"mailto:{sender.strip() or 'recruiting@' + settings.company_email_domain}"


def send_to_all(session: Session, payload: dict) -> int:
    """Send to every subscribed device. Devices the push service no longer knows are removed."""
    rows = session.scalars(select(PushSubscription)).all()
    if not rows:
        return 0
    vapid, _ = vapid_key(session)
    data = json.dumps(payload)
    sent = 0
    now = datetime.now(timezone.utc)
    for row in rows:
        try:
            webpush(
                {"endpoint": row.endpoint, "keys": {"p256dh": row.p256dh, "auth": row.auth}},
                data=data,
                vapid_private_key=vapid,
                vapid_claims={"sub": _subject()},
                ttl=24 * 3600,
                timeout=10,
            )
            row.last_sent_at = now
            sent += 1
        except WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            if status in (404, 410):
                session.delete(row)
            else:
                logger.warning("push to %s failed: %s", urlsplit(row.endpoint).hostname, exc)
        except Exception as exc:  # noqa: BLE001 - one bad device must not stop the others.
            logger.warning("push to %s failed: %s", urlsplit(row.endpoint).hostname, exc)
    session.commit()
    return sent


def send_application_push(notice) -> int:
    from app.db import admin_session

    verb = "New application" if notice.created else "Updated application"
    payload = {
        "title": f"{verb}: {notice.requisition_code}",
        "body": f"{notice.full_name} · {notice.title or 'Open role'}" + (f" · {notice.job_location}" if notice.job_location else ""),
        "url": f"/admin/submissions/{notice.submission_id}",
        "tag": f"application-{notice.submission_id}",
    }
    session = admin_session()
    try:
        return send_to_all(session, payload)
    except Exception as exc:  # noqa: BLE001 - the application is saved; alerts are best effort.
        logger.warning("application push failed: %s", exc)
        return 0
    finally:
        session.close()
