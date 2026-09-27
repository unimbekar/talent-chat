"""Public boundary: SQL log, database role, and import graph."""

import ast
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.db import public_engine, public_session
from app.main import create_app
from app.models import Candidate
from app.public.search import search_jobs
from tests.fakes import RecordingEmbedder, RecordingLLM

PUBLIC = Path(__file__).resolve().parents[1] / "app" / "public"


def test_import_boundary():
    violations = []
    for path in PUBLIC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    modules.append(node.module)
                modules.extend(alias.name for alias in node.names)
            for module in modules:
                if module.startswith("app.admin") or "candidate_repository" in module:
                    violations.append(f"{path.name}: {module}")
    assert violations == []


def test_public_role_cannot_read_candidates(_database):
    connection = psycopg.connect("postgresql://app_public:public@127.0.0.1:5432/talent_test")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        connection.execute("SELECT * FROM candidates")
    connection.close()


def test_public_search_and_route_do_not_touch_candidates(db):
    db.add(
        Candidate(
            file_sha256="abc",
            full_name="Casey Nguyen",
            status="confirmed",
            redacted_text="Casey Nguyen knows Java and lives in Chantilly.",
            outreach_opt_in=False,
        )
    )
    from app.models import Job

    db.add(
        Job(
            requisition_code="A1001",
            title="UI/UX Developer",
            location="Chantilly, VA",
            status="open",
            description_text="Build interfaces with JavaScript in Chantilly.",
            description_source="careers_page",
            must_have_skills=["JavaScript"],
            nice_to_have_skills=[],
        )
    )
    db.commit()
    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    engine = public_engine()
    event.listen(engine, "before_cursor_execute", record)
    try:
        session = public_session()
        search_jobs(session, "jobs in Chantilly", [], embedder=RecordingEmbedder())
        session.close()
        app = create_app()
        with TestClient(app) as client:
            app.state.llm = RecordingLLM()
            app.state.embedder = RecordingEmbedder()
            response = client.post("/public/chat", json={"message": "jobs in Chantilly", "prior_codes": []})
        assert response.status_code == 200
        body = response.json()
        assert "Casey Nguyen" not in response.text
        assert any(job["location"] == "Chantilly, VA" for job in body["jobs"])
    finally:
        event.remove(engine, "before_cursor_execute", record)
    joined = "\n".join(statements).lower()
    assert "candidates" not in joined
    assert "candidate_chunks" not in joined
