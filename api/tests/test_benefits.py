"""The recruiter desk can read the 2026–27 benefits guide and download the document."""

from fastapi.testclient import TestClient

from app.main import create_app
from tests.fakes import RecordingEmbedder, RecordingLLM


def _client() -> TestClient:
    app = create_app()
    client = TestClient(app)
    client.__enter__()
    app.state.llm = RecordingLLM()
    app.state.embedder = RecordingEmbedder()
    return client


def test_benefits_guide_is_for_a_signed_in_recruiter(db):
    client = _client()
    assert client.get("/admin/benefits").status_code == 401
    assert client.get("/admin/benefits/download").status_code == 401
    assert client.post("/admin/login", json={"email": "admin@janus-soft.com", "password": "correct-horse"}).status_code == 200

    guide = client.get("/admin/benefits")
    assert guide.status_code == 200
    body = guide.json()
    assert body["season"] == "2026–27"
    assert body["source"] == "Janus-Soft-Benefits-Details-2026-27.docx"
    text = str(body)
    assert "Unlimited paid time off" in text
    assert "10%" in text
    assert "50%" in text
    assert "$10,000.00" in text
    assert "$3,000.00" in text
    assert "4 weeks" not in text

    download = client.get("/admin/benefits/download")
    assert download.status_code == 200
    assert download.content.startswith(b"PK")
    assert "wordprocessingml" in download.headers["content-type"]
    assert "Janus-Soft-Benefits-2026-27.docx" in download.headers["content-disposition"]

    image = client.get("/admin/benefits/media/health.jpg")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/jpeg"
    assert client.get("/admin/benefits/media/../benefits.json").status_code == 404


def test_candidates_can_read_every_benefit_without_signing_in(db):
    client = _client()
    guide = client.get("/public/benefits")
    assert guide.status_code == 200
    body = guide.json()
    assert body["season"] == "2026–27"
    assert len(body["sections"]) == 8
    assert "filename" not in body
    text = str(body)
    assert "Unlimited paid time off" in text
    assert "100%" in text
    assert "10%" in text
    assert "50%" in text
    assert "$10,000.00" in text
    assert "$3,000.00" in text
    assert "$1,000.00" in text
    image = client.get("/public/benefits/media/health.jpg")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/jpeg"
    assert client.get("/public/benefits/media/../benefits.json").status_code == 404
