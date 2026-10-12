"""Admin session cookie and per-IP lockout."""

from datetime import datetime, timedelta, timezone
import uuid

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AdminPassword, AdminSession, DeskUser, LoginAttempt

_HASHER = PasswordHasher()
# Compared against when the email has no account, so a wrong email takes as long as a wrong password.
_DUMMY_HASH = _HASHER.hash("no-such-account")
_COOKIE = "admin_session"
_MAX_AGE = 12 * 3600
_LOCK_AFTER = 8
_LOCK_MINUTES = 15


def cookie_name() -> str:
    return _COOKIE


def active_hash(session: Session | None) -> str:
    """The hash set on the desk wins. Otherwise the file or environment hash."""
    if session is not None:
        row = session.get(AdminPassword, 1)
        if row is not None and row.password_hash.strip():
            return row.password_hash.strip()
    return get_settings().resolved_admin_hash()


def verify_password(password: str, session: Session | None = None) -> bool:
    hashed = active_hash(session)
    if not hashed or not password:
        return False
    try:
        return _HASHER.verify(hashed, password)
    except VerifyMismatchError:
        return False


def save_password(session: Session, password: str) -> None:
    hashed = _HASHER.hash(password)
    row = session.get(AdminPassword, 1)
    if row is None:
        session.add(AdminPassword(id=1, password_hash=hashed))
    else:
        row.password_hash = hashed
        row.updated_at = datetime.now(timezone.utc)


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().session_secret, salt="admin-session")


def hash_password(password: str) -> str:
    return _HASHER.hash(password)


def find_user(session: Session, email: str) -> DeskUser | None:
    return session.scalar(select(DeskUser).where(DeskUser.email == email.strip().lower()))


def verify_user(session: Session, email: str, password: str) -> DeskUser | None:
    """The active account with that email and password, or None. Always spends one hash check."""
    user = find_user(session, email)
    target = user.password_hash if user is not None else _DUMMY_HASH
    try:
        ok = bool(password) and _HASHER.verify(target, password)
    except VerifyMismatchError:
        ok = False
    if not ok or user is None or not user.active:
        return None
    return user


def end_sessions(session: Session, user_id: uuid.UUID) -> None:
    for row in session.scalars(select(AdminSession).where(AdminSession.user_id == user_id)):
        session.delete(row)


def issue_session(
    session: Session,
    *,
    email: str = "",
    google_refresh: str = "",
    role: str = "admin",
    user_id: uuid.UUID | None = None,
) -> str:
    row = AdminSession(
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=_MAX_AGE),
        role=role,
        email=email or None,
        user_id=user_id,
    )
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
    if row.user_id is not None:
        user = session.get(DeskUser, row.user_id)
        if user is None or not user.active or user.role != row.role:
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
