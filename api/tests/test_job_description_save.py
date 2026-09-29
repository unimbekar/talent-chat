"""Saving a job description returns before the model reads it."""

import json

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.admin.routes import _enrich_admin_description
from app.main import create_app
from app.models import Job, JobChunk
from tests.fakes import RecordingEmbedder


class JobLLM:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, *, system: str, user: str, temperature: float, json_mode: bool) -> str:
        self.calls += 1
        return json.dumps(
            {
                "summary": "Senior data scientist for deepfake detection.",
                "must_have_skills": ["Python"],
                "nice_to_have_skills": [],
                "clearance_required": "Secret",
            }
        )


def _seed(db) -> Job:
    job = Job(
        requisition_code="G2002",
        title="Data Scientist",
        location="Herndon, VA",
        status="open",
        description_text="Old text.",
        description_source="careers_page",
        must_have_skills=["Java"],
        nice_to_have_skills=[],
    )
    db.add(job)
    db.commit()
    return job


def test_save_stores_text_and_keeps_recruiter_skills(db):
    _seed(db)
    llm = JobLLM()
    app = create_app()
    with TestClient(app) as client:
        app.state.llm = llm
        app.state.embedder = RecordingEmbedder()
        assert client.post("/admin/login", json={"password": "correct-horse"}).status_code == 200
        response = client.put(
            "/admin/jobs/G2002",
            json={
                "description_text": "Senior data scientist with Python and deepfake work.",
                "must_have_quotes": ["Java"],
                "nice_to_have_quotes": [],
            },
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["description_text"] == "Senior data scientist with Python and deepfake work."
    assert body["description_source"] == "admin"

    db.expire_all()
    job = db.scalar(select(Job).where(Job.requisition_code == "G2002"))
    assert llm.calls == 1
    assert job.summary == "Senior data scientist for deepfake detection."
    assert job.clearance_required == "secret"
    assert job.must_have_skills == ["Java"]
    assert job.embedding is not None
    assert db.scalar(select(JobChunk).where(JobChunk.job_id == job.id)) is not None


def test_background_read_skips_a_replaced_description(db):
    job = _seed(db)
    llm = JobLLM()
    _enrich_admin_description(job.id, "stale-digest", False, llm, RecordingEmbedder())
    db.expire_all()
    assert llm.calls == 0
    assert db.get(Job, job.id).summary is None
