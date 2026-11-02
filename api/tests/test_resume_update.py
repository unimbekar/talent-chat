"""Admins and recruiters justify missing requirements and download an updated résumé."""

from io import BytesIO
from pathlib import Path

import pytest
from docx import Document
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.admin.resume_docx import build_updated_resume, justification_error
from app.admin.team_routes import create_account
from app.main import create_app
from app.models import Candidate, DeskUser, Job
from tests.fakes import RecordingEmbedder, RecordingLLM

RESUME = """Software Engineer
Alex Rivera
alex@example.com

Summary
Software engineer with 8 years of Java.

Experience
Acme
January 2018 - Present
Built Java services for a federal program and kept them running in production.
"""

JAVA = "5+ years of Java development"
KUBERNETES = "Experience with Kubernetes"
TERRAFORM = "Terraform modules for cloud accounts"
KUBE_NOTE = "Alex ran Kubernetes clusters for the Acme platform from 2021 through 2024."
FORM_NOTE = "Terraform was used on the same program to provision the AWS accounts."
KUBE_NOTE_2 = "Alex was the on-call lead for the Kubernetes platform, including upgrades and incident response."


def _client() -> TestClient:
    app = create_app()
    client = TestClient(app)
    client.__enter__()
    app.state.llm = RecordingLLM()
    app.state.embedder = RecordingEmbedder()
    return client


def _admin() -> TestClient:
    client = _client()
    assert client.post("/admin/login", json={"password": "correct-horse"}).status_code == 200
    return client


def _recruiter(db) -> TestClient:
    email = "recruiter@janus-soft.com"
    if db.scalar(select(DeskUser).where(DeskUser.email == email)) is None:
        create_account(db, email=email, password="recruit-test-pass-1", role="recruiter", display_name="Riley Recruiter")
        db.commit()
    client = _client()
    response = client.post("/admin/login", json={"email": email, "password": "recruit-test-pass-1"})
    assert response.status_code == 200
    return client


def _seed(db, digest: str = "alex-update") -> tuple[Job, Candidate, Path]:
    job = Job(
        requisition_code="J1001",
        title="Software Engineer",
        location="Reston, VA",
        status="open",
        description_text="Build Java services on Kubernetes.",
        description_source="admin",
        must_have_skills=["Java", "Kubernetes"],
        nice_to_have_skills=["Terraform"],
        skill_quotes={"must": [JAVA, KUBERNETES], "nice": [TERRAFORM]},
    )
    original = Path("/tmp/talent-chat-test-uploads") / f"{digest}.bin"
    original.parent.mkdir(parents=True, exist_ok=True)
    original.write_bytes(b"ORIGINAL-RESUME-BYTES")
    person = Candidate(
        file_sha256=digest,
        full_name="Alex Rivera",
        email="alex@example.com",
        location="Reston, VA",
        original_filename="Alex-Rivera.pdf",
        original_path=str(original),
        status="confirmed",
        skills=[],
        titles=["Software Engineer"],
        redacted_text=RESUME,
    )
    db.add_all([job, person])
    db.commit()
    return job, person, original


def _paragraphs(payload: bytes) -> str:
    document = Document(BytesIO(payload))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def test_a_short_note_is_refused_and_a_sentence_is_kept():
    assert justification_error("too short")
    assert justification_error("word " * 500)
    note = "Alex ran Kubernetes clusters for the Acme platform from 2021 through 2024."
    assert justification_error(note) is None
    payload = build_updated_resume(
        name="Alex Rivera",
        code="J1001",
        title="Software Engineer",
        filename="Alex-Rivera.pdf",
        author="Riley Recruiter",
        items=[{"line": KUBERNETES, "kind": "Mandatory", "justification": note}],
        resume_text=RESUME,
    )
    text = _paragraphs(payload)
    assert "Alex Rivera" in text
    assert KUBERNETES in text
    assert note in text
    assert "Built Java services" in text
    assert "Alex-Rivera.pdf" in text


@pytest.mark.parametrize("role", ["admin", "recruiter"])
def test_either_role_saves_twice_and_downloads_the_latest_notes(db, role):
    _job, person, original = _seed(db, digest=f"alex-{role}")
    client = _admin() if role == "admin" else _recruiter(db)
    params = {"code": "J1001", "candidate_id": str(person.id)}

    first = client.get("/admin/resume-update", params=params)
    assert first.status_code == 200
    lines = [item["line"] for item in first.json()["missing"]]
    assert KUBERNETES in lines
    assert TERRAFORM in lines
    assert JAVA not in lines
    assert first.json()["complete"] is False

    partial = client.put(
        "/admin/resume-update",
        json={"requisition_code": "J1001", "candidate_id": str(person.id), "items": [{"line": KUBERNETES, "justification": KUBE_NOTE}]},
    )
    assert partial.status_code == 200
    assert partial.json()["complete"] is False
    blocked = client.get("/admin/resume-update/file", params=params)
    assert blocked.status_code == 400

    short = client.put(
        "/admin/resume-update",
        json={"requisition_code": "J1001", "candidate_id": str(person.id), "items": [{"line": KUBERNETES, "justification": "too short"}]},
    )
    assert short.status_code == 400

    covered = client.put(
        "/admin/resume-update",
        json={"requisition_code": "J1001", "candidate_id": str(person.id), "items": [{"line": JAVA, "justification": KUBE_NOTE}]},
    )
    assert covered.status_code == 400

    saved = client.put(
        "/admin/resume-update",
        json={
            "requisition_code": "J1001",
            "candidate_id": str(person.id),
            "items": [
                {"line": KUBERNETES, "justification": KUBE_NOTE},
                {"line": TERRAFORM, "justification": FORM_NOTE},
            ],
        },
    )
    assert saved.status_code == 200
    assert saved.json()["complete"] is True

    first_file = client.get("/admin/resume-update/file", params=params)
    assert first_file.status_code == 200
    assert first_file.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    assert "updated.docx" in first_file.headers["content-disposition"]
    first_text = _paragraphs(first_file.content)
    assert KUBE_NOTE in first_text
    assert FORM_NOTE in first_text
    assert "Built Java services" in first_text

    revised = client.put(
        "/admin/resume-update",
        json={
            "requisition_code": "J1001",
            "candidate_id": str(person.id),
            "items": [
                {"line": KUBERNETES, "justification": KUBE_NOTE_2},
                {"line": TERRAFORM, "justification": FORM_NOTE},
            ],
        },
    )
    assert revised.status_code == 200
    second_file = client.get("/admin/resume-update/file", params=params)
    second_text = _paragraphs(second_file.content)
    assert KUBE_NOTE_2 in second_text
    assert KUBE_NOTE not in second_text
    assert original.read_bytes() == b"ORIGINAL-RESUME-BYTES"


def test_a_visitor_cannot_update_or_download(db):
    _job, person, _original = _seed(db, digest="alex-locked")
    client = _client()
    params = {"code": "J1001", "candidate_id": str(person.id)}
    assert client.get("/admin/resume-update", params=params).status_code == 401
    assert client.put("/admin/resume-update", json={"requisition_code": "J1001", "candidate_id": str(person.id), "items": []}).status_code == 401
    assert client.get("/admin/resume-update/file", params=params).status_code == 401


def test_download_waits_when_nothing_is_missing(db):
    job, person, _original = _seed(db, digest="alex-covered")
    job.skill_quotes = {"must": [JAVA], "nice": []}
    job.must_have_skills = ["Java"]
    job.nice_to_have_skills = []
    db.commit()
    client = _admin()
    view = client.get("/admin/resume-update", params={"code": "J1001", "candidate_id": str(person.id)})
    assert view.status_code == 200
    assert view.json()["missing"] == []
    refused = client.get("/admin/resume-update/file", params={"code": "J1001", "candidate_id": str(person.id)})
    assert refused.status_code == 400
    assert "original" in refused.json()["detail"].lower()
