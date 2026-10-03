"""Job cards come back before the model writes the paragraph."""

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import Job
from app.public.routes import reset_rate_limit
from tests.fakes import RecordingEmbedder, RecordingLLM


def _seed(db) -> None:
    db.add_all(
        [
            Job(
                requisition_code="A1001",
                title="UI/UX Developer",
                location="Chantilly, VA",
                status="open",
                description_text="Design interfaces with JavaScript in Chantilly.",
                description_source="careers_page",
                must_have_skills=["JavaScript"],
                nice_to_have_skills=[],
            ),
            Job(
                requisition_code="A1003",
                title="Software Developer",
                location="Herndon, VA",
                status="open",
                description_text="Build Java and AWS services.",
                description_source="careers_page",
                must_have_skills=["Java", "AWS"],
                nice_to_have_skills=[],
            ),
        ]
    )
    db.commit()


def test_cards_first_then_paragraph(db):
    _seed(db)
    reset_rate_limit()
    llm = RecordingLLM(text="A1001 in Chantilly fits, and the invented Z9999 does not exist.")
    app = create_app()
    with TestClient(app) as client:
        app.state.llm = llm
        app.state.embedder = RecordingEmbedder()
        cards = client.post("/public/chat", json={"message": "Jobs in Chantilly", "prior_codes": [], "explain": False})
        assert cards.status_code == 200
        body = cards.json()
        assert body["explain_pending"] is True
        assert body["answer"] == ""
        assert llm.prompts == []
        codes = [job["requisition_code"] for job in body["jobs"]]
        assert codes == ["A1001"]

        paragraph = client.post("/public/explain", json={"message": "Jobs in Chantilly", "prior_codes": [], "codes": codes})
        assert paragraph.status_code == 200
        answer = paragraph.json()["answer"]
        assert "A1001" in answer
        assert "Z9999" not in answer
        assert len(llm.prompts) == 1
        assert "A1003" not in llm.prompts[0]["user"]


def test_explain_reports_model_outage(db):
    _seed(db)
    reset_rate_limit()
    app = create_app()
    with TestClient(app) as client:
        app.state.llm = RecordingLLM(fail=True)
        app.state.embedder = RecordingEmbedder()
        response = client.post("/public/explain", json={"message": "Jobs in Chantilly", "prior_codes": [], "codes": ["A1001"]})
    assert response.status_code == 200
    assert response.json() == {"answer": "", "notice": "Explanations are unavailable right now."}
