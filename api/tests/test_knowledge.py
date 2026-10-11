"""Handbook upload, retrieval, and the public careers chat."""

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import public_session
from app.knowledge.graph import build_rag_graph
from app.knowledge.intent import wants_jobs, wants_policy
from app.main import create_app
from tests.fakes import RecordingEmbedder, RecordingLLM

HANDBOOK = (
    "Health insurance. Full-time employees may enroll in the medical plan on the first of the month after the start date. "
    "The company pays 80 percent of the employee premium. Dental and vision are optional. "
    "Retirement. The 401k match is 6 percent of eligible pay when the employee contributes at least 6 percent. "
    "Vesting is immediate. This section is the careers handbook."
)
PAPER = (
    "Scaled dot product attention compares queries and keys before a softmax. "
    "This note is for developers reading a research summary and is not a company benefit or policy. "
    "It stays off the careers site."
)


def _client() -> tuple[TestClient, RecordingLLM, RecordingEmbedder]:
    app = create_app()
    client = TestClient(app)
    client.__enter__()
    llm = RecordingLLM(text="The handbook says the 401k match is 6 percent.")
    embedder = RecordingEmbedder()
    app.state.llm = llm
    app.state.embedder = embedder
    return client, llm, embedder


def _login(client: TestClient) -> None:
    assert client.post("/admin/login", json={"email": "admin@janus-soft.com", "password": "correct-horse"}).status_code == 200


def test_intent_splits_documents_from_jobs():
    assert wants_policy("What is the 401k match?")
    assert not wants_jobs("What is the 401k match?")
    assert wants_jobs("Jobs in Chantilly")
    assert not wants_policy("Jobs in Chantilly")
    assert wants_policy("Does the AWS role include dental insurance?")
    assert wants_jobs("Does the AWS role include dental insurance?")
    assert wants_policy("How do I submit a timesheet?")
    assert not wants_jobs("How do I submit a timesheet?")
    assert wants_jobs("Java and AWS")
    assert not wants_policy("Java and AWS")


def test_handbook_answers_and_hides_internal_notes(db):
    client, llm, embedder = _client()
    assert client.get("/admin/knowledge").status_code == 401
    _login(client)
    short = client.post("/admin/knowledge", data={"title": "Tiny", "audience": "public", "text": "too short"})
    assert short.status_code == 400
    created = client.post(
        "/admin/knowledge",
        data={"title": "Health benefits", "audience": "public", "text": HANDBOOK},
    )
    assert created.status_code == 200
    document_id = created.json()["id"]
    assert created.json()["chunks"] >= 1
    hidden = client.post(
        "/admin/knowledge",
        data={"title": "Attention note", "audience": "internal", "text": PAPER},
    )
    assert hidden.status_code == 200

    asked = client.post("/public/chat", json={"message": "What is the 401k match?", "prior_codes": []})
    assert asked.status_code == 200
    body = asked.json()
    assert body["jobs"] == []
    assert body["sources"][0]["title"] == "Health benefits"
    assert "6 percent" in body["sources"][0]["excerpt"]
    assert "Attention" not in body["answer"]
    assert any("401k match is 6 percent" in prompt["user"] for prompt in llm.prompts)

    jobs = client.post("/public/chat", json={"message": "Jobs in Chantilly", "prior_codes": []})
    assert jobs.json().get("sources") in (None, [])
    assert "401k" not in (jobs.json().get("answer") or "")
    assert "401k" not in (jobs.json().get("answer") or "").lower()

    graph = build_rag_graph(db, embedder, llm, audience="public")
    assert {"retrieve", "draft"} <= set(graph.get_graph().nodes)

    edited = client.put(
        f"/admin/knowledge/{document_id}",
        json={"title": "Health benefits", "audience": "public", "body": HANDBOOK.replace("6 percent", "4 percent")},
    )
    assert edited.status_code == 200
    again = client.post("/public/chat", json={"message": "What is the 401k match?", "prior_codes": []})
    assert "4 percent" in again.json()["sources"][0]["excerpt"]
    assert "6 percent" not in again.json()["sources"][0]["excerpt"]

    assert client.delete(f"/admin/knowledge/{document_id}").status_code == 200
    gone = client.post("/public/chat", json={"message": "What is the 401k match?", "prior_codes": []})
    assert gone.json()["answer"] == "That is not in the knowledge base on file."
    assert gone.json()["sources"] == []

    public = public_session()
    denied = False
    try:
        public.execute(text("SELECT title FROM knowledge_documents"))
    except Exception:
        denied = True
        public.rollback()
    finally:
        public.close()
    assert denied


def test_a_procedure_document_answers_without_being_a_handbook(db):
    client, llm, _embedder = _client()
    _login(client)
    created = client.post(
        "/admin/knowledge",
        data={
            "title": "Timesheet procedure",
            "audience": "public",
            "text": (
                "Timesheets are submitted in the payroll portal by Friday at noon. "
                "A missing timesheet delays pay until the next cycle. "
                "This procedure is a company document, not a job posting."
            ),
        },
    )
    assert created.status_code == 200
    asked = client.post("/public/chat", json={"message": "How do I submit a timesheet?", "prior_codes": []})
    body = asked.json()
    assert body["jobs"] == []
    assert body["sources"][0]["title"] == "Timesheet procedure"
    assert "Friday" in body["sources"][0]["excerpt"]
    assert any("Timesheet procedure" in prompt["user"] for prompt in llm.prompts)
    skills = client.post("/public/chat", json={"message": "Java and AWS", "prior_codes": []})
    assert "Friday" not in (skills.json().get("answer") or "")
    assert skills.json().get("sources") in (None, [])
