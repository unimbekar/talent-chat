"""Who is signed in to the desk, and what their role allows.

Admins can do everything. Recruiters work candidates and the pipeline, but cannot delete
anything, see the burden calculator or margins, change settings, edit job postings, run bulk
ingest, change company documents, export reports, or manage accounts.
"""

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.admin.auth import cookie_name, read_session
from app.db import get_admin_db

ROLES = ("admin", "recruiter")

# What the web app shows or hides. The API checks each one again.
CAPABILITIES = {
    "delete": "delete records",
    "burden": "use the burden calculator",
    "settings": "change desk settings",
    "edit_jobs": "edit, close, reopen, or recrawl jobs",
    "bulk_ingest": "run a folder or cloud import",
    "knowledge_edit": "add, edit, or remove company documents",
    "export": "export reports",
    "team": "manage desk accounts",
    "visitors": "see careers-site visitor numbers",
}


def require_desk(request: Request, session: Session = Depends(get_admin_db)) -> Session:
    """Any signed-in desk account."""
    row = read_session(session, request.cookies.get(cookie_name()))
    if row is None:
        raise HTTPException(status_code=401, detail="Sign in required.")
    session.info["role"] = row.role
    session.info["actor"] = row.email or "admin"
    session.info["user_id"] = row.user_id
    session.info["session_id"] = row.id
    return session


def role_of(session: Session) -> str:
    """The signed-in role. Code that runs outside a request acts as admin."""
    return session.info.get("role", "admin")


def is_admin(session: Session) -> bool:
    return role_of(session) == "admin"


def actor_of(session: Session) -> str:
    return session.info.get("actor", "admin")


def admin_only(capability: str) -> Callable[..., Session]:
    """A dependency that lets admins through and tells a recruiter what they cannot do."""
    action = CAPABILITIES[capability]

    def guard(session: Session = Depends(require_desk)) -> Session:
        if not is_admin(session):
            raise HTTPException(
                status_code=403,
                detail={"message": f"Recruiter accounts cannot {action}. Ask an admin.", "capability": capability},
            )
        return session

    guard.__name__ = f"admin_only_{capability}"
    return guard


def capabilities(role: str) -> dict[str, bool]:
    return {key: role == "admin" for key in CAPABILITIES}
