"""Shared database fixture for Phase 1 acceptance tests."""

import os
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://app_admin:admin@127.0.0.1:5432/talent_test")
os.environ.setdefault("DATABASE_PUBLIC_URL", "postgresql+psycopg://app_public:public@127.0.0.1:5432/talent_test")
os.environ.setdefault("DATABASE_MIGRATE_URL", "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/talent_test")
for _name in ("DATABASE_URL", "DATABASE_PUBLIC_URL", "DATABASE_MIGRATE_URL"):
    # The db fixture truncates every table. A URL left in the shell must never point it at real data.
    if not os.environ[_name].rsplit("/", 1)[-1].split("?", 1)[0].endswith("_test"):
        raise SystemExit(f"{_name} must name a *_test database for the test suite, not {os.environ[_name].rsplit('/', 1)[-1]}")
os.environ.setdefault("CRAWL_ON_START", "false")
os.environ.setdefault("WARM_RESUME_CACHE", "false")
os.environ.setdefault("SESSION_SECRET", "test-session-secret")
os.environ.setdefault("FILE_DIR", "/tmp/talent-chat-test-uploads")
os.environ["ADMIN_PASSWORD_HASH"] = ""

from argon2 import PasswordHasher  # noqa: E402

os.environ["ADMIN_PASSWORD_HASH"] = PasswordHasher().hash("correct-horse")

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
import psycopg  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import admin_session, reset_engines  # noqa: E402

get_settings.cache_clear()
reset_engines()


@pytest.fixture(scope="session")
def _database():
    admin = psycopg.connect("postgresql://postgres:postgres@127.0.0.1:5432/postgres", autocommit=True)
    admin.execute("SELECT 1 FROM pg_database WHERE datname = 'talent_test'").fetchone()
    exists = admin.execute("SELECT 1 FROM pg_database WHERE datname = 'talent_test'").fetchone()
    if not exists:
        admin.execute("CREATE DATABASE talent_test")
    admin.close()
    command.upgrade(Config("alembic.ini"), "head")
    role = psycopg.connect("postgresql://postgres:postgres@127.0.0.1:5432/talent_test", autocommit=True)
    role.execute("ALTER ROLE app_admin PASSWORD 'admin'")
    role.execute("ALTER ROLE app_public PASSWORD 'public'")
    role.close()
    Path("/tmp/talent-chat-test-uploads").mkdir(parents=True, exist_ok=True)
    yield


@pytest.fixture
def db(_database):
    session = admin_session()
    session.execute(
        text(
            "TRUNCATE job_applications, submission_comments, candidate_comments, submission_events, submissions, "
            "matches, candidate_chunks, job_chunks, candidates, jobs, "
            "audit_log, admin_sessions, login_attempts RESTART IDENTITY CASCADE"
        )
    )
    session.execute(
        text("UPDATE crawl_state SET last_ok = NULL, last_error = NULL, last_rows = NULL, last_finished_at = NULL")
    )
    session.commit()
    yield session
    session.close()
