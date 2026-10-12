"""Desk accounts: admins add recruiters, reset passwords, and turn accounts off."""

from datetime import datetime, timezone
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.admin.access import ROLES, admin_only
from app.admin.auth import end_sessions, find_user, hash_password
from app.admin.routes import _audit, local_admin_email
from app.models import AdminSession, DeskUser

router = APIRouter(prefix="/admin/team", tags=["team"])

PASSWORD_MIN = 12
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_team = admin_only("team")


class AccountIn(BaseModel):
    email: str
    password: str
    role: str = "recruiter"
    display_name: str | None = None


class AccountPatch(BaseModel):
    display_name: str | None = None
    role: str | None = None
    active: bool | None = None
    password: str | None = None


def _fail(status: int, message: str) -> None:
    raise HTTPException(status_code=status, detail={"message": message})


def _email(value: str) -> str:
    email = value.strip().lower()
    if not _EMAIL.match(email) or len(email) > 254:
        _fail(400, "Enter a full email address, such as name@janus-soft.com.")
    if email == local_admin_email():
        _fail(409, "That email is the built-in admin sign-in.")
    return email


def _role(value: str) -> str:
    if value not in ROLES:
        _fail(400, "Role must be admin or recruiter.")
    return value


def _password(value: str) -> str:
    if len(value) < PASSWORD_MIN:
        _fail(400, f"Use at least {PASSWORD_MIN} characters for the password.")
    if len(value) > 200:
        _fail(400, "Keep the password under 200 characters.")
    return value


def _name(value: str | None) -> str | None:
    text = (value or "").strip()
    if len(text) > 120:
        _fail(400, "Keep the name under 120 characters.")
    return text or None


def create_account(session: Session, *, email: str, password: str, role: str = "recruiter", display_name: str | None = None) -> DeskUser:
    email = _email(email)
    if find_user(session, email) is not None:
        _fail(409, f"{email} already has an account.")
    now = datetime.now(timezone.utc)
    user = DeskUser(
        email=email,
        display_name=_name(display_name),
        role=_role(role),
        password_hash=hash_password(_password(password)),
        active=True,
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    session.flush()
    return user


def _out(session: Session, user: DeskUser) -> dict:
    now = datetime.now(timezone.utc)
    live = session.scalar(
        select(func.count()).select_from(AdminSession).where(AdminSession.user_id == user.id, AdminSession.expires_at > now)
    )
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "active": user.active,
        "builtin": False,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "signed_in": bool(live),
    }


def _load(session: Session, user_id: uuid.UUID) -> DeskUser:
    user = session.get(DeskUser, user_id)
    if user is None:
        _fail(404, "That account is not on file.")
    return user


@router.get("")
def list_accounts(session: Session = Depends(_team)):
    users = session.scalars(select(DeskUser).order_by(DeskUser.role, DeskUser.email)).all()
    builtin = {
        "id": "builtin",
        "email": local_admin_email(),
        "display_name": "Desk admin",
        "role": "admin",
        "active": True,
        "builtin": True,
        "created_at": None,
        "last_login_at": None,
        "signed_in": None,
    }
    return {"accounts": [builtin, *(_out(session, user) for user in users)], "password_min": PASSWORD_MIN}


@router.post("")
def add_account(body: AccountIn, session: Session = Depends(_team)):
    user = create_account(session, email=body.email, password=body.password, role=body.role, display_name=body.display_name)
    _audit(session, "team_add", user.id, f"{user.role}:{user.email}"[:200])
    session.commit()
    return _out(session, user)


@router.patch("/{user_id}")
def update_account(user_id: uuid.UUID, body: AccountPatch, session: Session = Depends(_team)):
    user = _load(session, user_id)
    sent = body.model_fields_set
    changes = []
    sign_out = False
    if "display_name" in sent:
        user.display_name = _name(body.display_name)
        changes.append("name")
    if "role" in sent and body.role is not None and body.role != user.role:
        user.role = _role(body.role)
        changes.append(f"role:{user.role}")
        sign_out = True
    if "active" in sent and body.active is not None and body.active != user.active:
        user.active = body.active
        changes.append("active" if body.active else "inactive")
        sign_out = sign_out or not body.active
    if "password" in sent and body.password:
        user.password_hash = hash_password(_password(body.password))
        changes.append("password")
        sign_out = True
    if not changes:
        _fail(400, "Nothing to change.")
    user.updated_at = datetime.now(timezone.utc)
    if sign_out:
        end_sessions(session, user.id)
    _audit(session, "team_edit", user.id, ",".join(changes)[:200])
    session.commit()
    return _out(session, user)


@router.delete("/{user_id}")
def delete_account(user_id: uuid.UUID, session: Session = Depends(_team)):
    user = _load(session, user_id)
    end_sessions(session, user.id)
    _audit(session, "team_delete", user.id, user.email[:200])
    session.delete(user)
    session.commit()
    return {"ok": True}
