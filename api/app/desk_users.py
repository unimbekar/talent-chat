"""Add or reset a desk account from the command line.

    docker compose exec -it api python -m app.desk_users add recruiter@janus-soft.com --role recruiter --name "Recruiter"

The password is read from DESK_PASSWORD when set, otherwise asked for without echo.
It is never taken as an argument, so it stays out of shell history.
"""

import argparse
from datetime import datetime, timezone
from getpass import getpass
import os
import sys

from fastapi import HTTPException

from app.admin.auth import end_sessions, find_user, hash_password
from app.admin.team_routes import _password, create_account
from app.db import admin_session
from app.models import AuditLog


def _read_password() -> str:
    value = os.environ.get("DESK_PASSWORD", "")
    if value:
        return value
    first = getpass("Password: ")
    if first != getpass("Repeat password: "):
        raise SystemExit("The passwords do not match.")
    return first


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.desk_users")
    parser.add_argument("action", choices=["add", "reset"])
    parser.add_argument("email")
    parser.add_argument("--role", default="recruiter", choices=["admin", "recruiter"])
    parser.add_argument("--name", default=None)
    args = parser.parse_args(argv)
    password = _read_password()
    session = admin_session()
    session.info["actor"] = "cli"
    try:
        if args.action == "add":
            user = create_account(session, email=args.email, password=password, role=args.role, display_name=args.name)
            session.add(AuditLog(actor="cli", action="team_add", subject_id=user.id, outcome=f"{user.role}:{user.email}"))
        else:
            user = find_user(session, args.email)
            if user is None:
                raise SystemExit(f"No account for {args.email}.")
            user.password_hash = hash_password(_password(password))
            user.active = True
            user.updated_at = datetime.now(timezone.utc)
            end_sessions(session, user.id)
            session.add(AuditLog(actor="cli", action="team_edit", subject_id=user.id, outcome="password"))
        session.commit()
    except HTTPException as error:
        detail = error.detail if isinstance(error.detail, dict) else {"message": str(error.detail)}
        print(detail.get("message"), file=sys.stderr)
        return 1
    finally:
        session.close()
    print(f"{args.action}: {user.email} ({user.role})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
