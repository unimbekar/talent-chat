"""Admin session cookie and per-IP lockout."""

from datetime import datetime, timedelta, timezone
import uuid

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AdminSession, LoginAttempt

_HASHER = PasswordHasher()
_COOKIE = "admin_session"
_MAX_AGE = 12 * 3600
_LOCK_AFTER = 8
_LOCK_MINUTES = 15


def cookie_name() -> str:
    return _COOKIE


def verify_password(password: str) -> bool:
    hashed = get_settings().resolved_admin_hash()
    if not hashed or not password:
        return False
    try:
        return _HASHER.verify(hashed, password)
    except VerifyMismatchError:
        return False


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().session_secret, salt="admin-session")


def issue_session(session: Session, *, email: str = "", google_refresh: str = "") -> str:
    row = AdminSession(expires_at=datetime.now(timezone.utc) + timedelta(seconds=_MAX_AGE))
    session.add(row)
    session.flush()
    payload: dict[str, str] = {"sid": str(row.id)}
    if email:
        payload["email"] = email
    if google_refresh:
        payload["gr"] = google_refresh
    return _serializer().dumps(payload)


def session_claims(token: str | None) -> dict[str, str]:
    """Signed cookie fields. Empty when the cookie is missing or expired."""
    if not token:
        return {}
    try:
        data = _serializer().loads(token, max_age=_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return {}
    if not isinstance(data, dict):
        return {}
    return {key: value for key, value in data.items() if isinstance(value, str)}


def read_session(session: Session, token: str | None) -> AdminSession | None:
    if not token:
        return None
    try:
        data = _serializer().loads(token, max_age=_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    try:
        sid = uuid.UUID(data.get("sid", ""))
    except (ValueError, TypeError):
        return None
    row = session.get(AdminSession, sid)
    if row is None or row.expires_at < datetime.now(timezone.utc):
        return None
    return row


def lock_status(session: Session, ip: str) -> bool:
    row = session.scalar(select(LoginAttempt).where(LoginAttempt.ip == ip))
    if row is None or row.locked_until is None:
        return False
    return row.locked_until > datetime.now(timezone.utc)


def record_failure(session: Session, ip: str) -> None:
    now = datetime.now(timezone.utc)
    row = session.scalar(select(LoginAttempt).where(LoginAttempt.ip == ip))
    if row is None:
        row = LoginAttempt(ip=ip, failed_count=0)
        session.add(row)
    if row.locked_until and row.locked_until > now:
        session.commit()
        return
    if row.locked_until and row.locked_until <= now:
        row.failed_count = 0
        row.locked_until = None
    row.failed_count += 1
    if row.failed_count >= _LOCK_AFTER:
        row.locked_until = now + timedelta(minutes=_LOCK_MINUTES)
        row.failed_count = 0
    session.commit()


def clear_failures(session: Session, ip: str) -> None:
    row = session.scalar(select(LoginAttempt).where(LoginAttempt.ip == ip))
    if row is not None:
        row.failed_count = 0
        row.locked_until = None
        session.commit()
