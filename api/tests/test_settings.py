"""Desk settings: theme is public, model names stay off the public config, and a saved model waits for the next process."""

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import admin_session
from app.main import create_app
from tests.fakes import RecordingEmbedder, RecordingLLM


def _client() -> TestClient:
    app = create_app()
    client = TestClient(app)
    client.__enter__()
    app.state.llm = RecordingLLM()
    app.state.llm.model = "qwen3.6:latest"
    app.state.running_model = "qwen3.6:latest"
    app.state.running_assistant_model = "qwen3.6:latest"
    app.state.embedder = RecordingEmbedder()
    return client


def _clear() -> None:
    session = admin_session()
    session.execute(text("DELETE FROM settings WHERE key IN ('theme', 'local_models', 'llm_model', 'assistant_model')"))
    session.commit()
    session.close()


def test_login_options_do_not_name_the_account(db):
    client = _client()
    options = client.get("/admin/login/options")
    assert options.status_code == 200
    body = options.json()
    assert "local_email" not in body
    assert "admin@janus-soft.com" not in str(body)
    assert "password" in body


def test_theme_is_public_and_models_are_not(db):
    _clear()
    try:
        client = _client()
        assert client.get("/public/config").json()["theme"] == "dark"
        assert client.get("/admin/settings").status_code == 401
        assert client.post("/admin/login", json={"email": "admin@janus-soft.com", "password": "correct-horse"}).status_code == 200

        bad = client.put("/admin/settings", json={"theme": "sepia"})
        assert bad.status_code == 422

        saved = client.put("/admin/settings", json={"theme": "light"})
        assert saved.status_code == 200
        assert saved.json()["theme"] == "light"
        public = client.get("/public/config").json()
        assert public["theme"] == "light"
        assert "models" not in public
        assert "llm_model" not in public
        assert "qwen" not in str(public)

        client.put("/admin/settings", json={"theme": "dark"})
    finally:
        _clear()


def test_added_model_waits_for_the_next_process(db):
    _clear()
    try:
        client = _client()
        assert client.post("/admin/login", json={"email": "admin@janus-soft.com", "password": "correct-horse"}).status_code == 200
        view = client.get("/admin/settings").json()
        assert view["running_model"] == "qwen3.6:latest"
        assert view["deploy_required"] is False

        rejected = client.post("/admin/settings/models", json={"tag": "not a model", "label": "Bad"})
        assert rejected.status_code == 400
        assert client.post("/admin/settings/models", json={"tag": "http://weights.example/x"}).status_code == 400

        added = client.post(
            "/admin/settings/models",
            json={"tag": "llama3.2:latest", "label": "Llama 3.2", "note": "Local answers"},
        )
        assert added.status_code == 200
        tags = [row["tag"] for row in added.json()["models"]]
        assert "llama3.2:latest" in tags
        assert added.json()["running_model"] == "qwen3.6:latest"
        assert added.json()["deploy_required"] is False

        chosen = client.put("/admin/settings", json={"chat_model": "llama3.2:latest", "assistant_model": "llama3.2:latest"})
        assert chosen.status_code == 200
        body = chosen.json()
        assert body["chat_model"] == "llama3.2:latest"
        assert body["running_model"] == "qwen3.6:latest"
        assert body["deploy_required"] is True
        assert "docker compose up -d --build api" in body["deploy_command"]

        app = create_app()
        with TestClient(app):
            assert app.state.llm.model == "llama3.2:latest"
            assert app.state.running_assistant_model == "llama3.2:latest"

        missing = client.put("/admin/settings", json={"chat_model": "missing:latest"})
        assert missing.status_code == 400
        running = client.delete("/admin/settings/models", params={"tag": "qwen3.6:latest"})
        assert running.status_code == 409
        removed = client.delete("/admin/settings/models", params={"tag": "llama3.2:latest"})
        assert removed.status_code == 200
        assert removed.json()["chat_model"] == "qwen3.6:latest"
        assert removed.json()["deploy_required"] is False
    finally:
        _clear()
