"""A signed-in recruiter can replace the desk password. The public role cannot read the hash."""

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import admin_session, public_session
from app.main import create_app
from tests.fakes import RecordingEmbedder, RecordingLLM


def _client() -> TestClient:
    app = create_app()
    client = TestClient(app)
    client.__enter__()
    app.state.llm = RecordingLLM()
    app.state.embedder = RecordingEmbedder()
    return client


def test_password_change_replaces_the_hash(db):
    client = _client()
    assert client.post("/admin/password", json={"current_password": "correct-horse", "new_password": "brand-new-desk-pw"}).status_code == 401
    assert client.post("/admin/login", json={"email": "someone@example.com", "password": "correct-horse"}).status_code == 401
    signed = client.post("/admin/login", json={"email": "admin@janus-soft.com", "password": "correct-horse"})
    assert signed.status_code == 200
    assert signed.json()["email"] == "admin@janus-soft.com"
    assert client.get("/admin/session").json()["email"] == "admin@janus-soft.com"
    wrong = client.post("/admin/password", json={"current_password": "not-the-password", "new_password": "brand-new-desk-pw"})
    assert wrong.status_code == 400
    short = client.post("/admin/password", json={"current_password": "correct-horse", "new_password": "too-short"})
    assert short.status_code == 422
    changed = client.post("/admin/password", json={"current_password": "correct-horse", "new_password": "brand-new-desk-pw"})
    assert changed.status_code == 200
    client.post("/admin/logout")
    assert client.post("/admin/login", json={"password": "correct-horse"}).status_code == 401
    assert client.post("/admin/login", json={"password": "brand-new-desk-pw"}).status_code == 200

    public = public_session()
    denied = False
    try:
        public.execute(text("SELECT password_hash FROM admin_password"))
    except Exception:
        denied = True
        public.rollback()
    finally:
        public.close()
    assert denied
    admin = admin_session()
    try:
        row = admin.execute(text("SELECT password_hash FROM admin_password WHERE id = 1")).scalar_one()
    finally:
        admin.close()
    assert row.startswith("$argon2")
    assert "brand-new-desk-pw" not in row
