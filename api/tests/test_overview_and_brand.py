from fastapi.testclient import TestClient

from app.main import create_app
from app.models import Candidate, Job
from tests.fakes import RecordingEmbedder, RecordingLLM


def _client() -> TestClient:
    app = create_app()
    client = TestClient(app)
    client.__enter__()
    app.state.llm = RecordingLLM()
    app.state.embedder = RecordingEmbedder()
    return client


def test_public_config_carries_branding():
    client = _client()
    body = client.get("/public/config").json()
    assert body["company_name"]
    assert body["accent"].startswith("#")
    assert body["logo_url"] and body["hero_url"]
    assert isinstance(body["examples"], list) and body["examples"]


def test_overview_counts(db):
    db.add_all(
        [
            Job(requisition_code="A1", title="Dev", status="open", description_text="Java", must_have_skills=["Java"], nice_to_have_skills=[]),
            Job(requisition_code="A2", title="Old", status="closed", description_text="", must_have_skills=[], nice_to_have_skills=[]),
            Candidate(
                file_sha256="x1",
                full_name="Pat Lee",
                location="Reston, VA",
                status="confirmed",
                skills=[{"name": "Java", "years": None}, {"name": "AWS", "years": None}],
                titles=["Developer"],
            ),
            Candidate(file_sha256="x2", full_name="Sam Roe", skills=[{"name": "Java", "years": None}], titles=[]),
        ]
    )
    db.commit()
    client = _client()
    assert client.get("/admin/overview").status_code == 401
    assert client.post("/admin/login", json={"password": "correct-horse"}).status_code == 200
    body = client.get("/admin/overview").json()
    assert body["jobs"] == {"open": 1, "closed": 1, "needs_review": 0, "no_description": 0}
    assert body["candidates"]["total"] == 2
    assert body["candidates"]["ranked"] == 1
    assert body["candidates"]["no_location"] == 1
    assert body["top_skills"][0] == {"name": "Java", "count": 2}
    assert body["top_states"] == [{"state": "VA", "count": 1}]
    assert len(body["recent_candidates"]) == 2
