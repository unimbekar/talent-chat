"""Deleting a job removes its pipeline rows. A later crawl brings the code back when the careers page still lists it."""

from datetime import date
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.crawler import MapFetcher, run_crawl
from app.main import create_app
from app.models import Candidate, Job, JobApplication, RemovedJob, Submission
from tests.fakes import RecordingEmbedder, RecordingLLM

CAREERS = "https://www.janus-soft.com/career"
LISTING = """
<html><body>
<p><a href="https://janus-soft.com/jobs/1001">A1001 - UI/UX Developer - Chantilly VA</a></p>
<p><a href="https://janus-soft.com/jobs/1002">A1002 - Software Developer - Herndon VA</a></p>
</body></html>
"""


def _client() -> TestClient:
    client = TestClient(create_app())
    client.__enter__()
    assert client.post("/admin/login", json={"password": "correct-horse"}).status_code == 200
    return client


def test_delete_removes_the_job_and_its_submissions(db):
    job = Job(
        requisition_code="A1001",
        title="UI/UX Developer",
        location="Chantilly, VA",
        status="closed",
        close_note="filled",
        closed_manually=True,
        description_text="Build.",
        must_have_skills=[],
        nice_to_have_skills=[],
    )
    person = Candidate(
        file_sha256=uuid.uuid4().hex,
        full_name="Casey Applicant",
        email="casey@example.com",
        status="confirmed",
        skills=[],
        titles=[],
    )
    db.add_all([job, person])
    db.flush()
    submission = Submission(candidate_id=person.id, job_id=job.id, stage="submitted")
    db.add(submission)
    db.flush()
    db.add(
        JobApplication(
            submission_id=submission.id,
            candidate_id=person.id,
            job_id=job.id,
            full_name="Casey Applicant",
            email="casey@example.com",
            phone="703-555-0199",
            location="McLean, VA",
            salary_usd=150000,
            start_on=date(2026, 4, 1),
            years_experience=8,
            fsp=True,
        )
    )
    db.commit()
    response = _client().delete("/admin/jobs/A1001")
    assert response.status_code == 200
    assert response.json()["requisition_code"] == "A1001"
    db.expire_all()
    assert db.scalar(select(Job).where(Job.requisition_code == "A1001")) is None
    assert db.scalar(select(Submission.id)) is None
    assert db.scalar(select(JobApplication.id)) is None
    assert db.get(Candidate, person.id) is not None
    assert db.get(RemovedJob, "A1001") is not None
    missing = _client().delete("/admin/jobs/A1001")
    assert missing.status_code == 404


def test_recrawl_brings_back_a_deleted_job_that_is_still_listed(db):
    db.add(
        Job(
            requisition_code="A1001",
            title="Old title",
            location="Reston, VA",
            status="closed",
            close_note="filled",
            closed_manually=True,
            description_text="Build.",
            must_have_skills=[],
            nice_to_have_skills=[],
        )
    )
    db.commit()
    assert _client().delete("/admin/jobs/A1001").status_code == 200
    db.expire_all()
    assert db.get(RemovedJob, "A1001") is not None
    assert db.scalar(select(Job).where(Job.requisition_code == "A1001")) is None

    state = run_crawl(db, MapFetcher({CAREERS: LISTING}), CAREERS, RecordingLLM(), RecordingEmbedder())
    assert state.last_ok is True
    db.expire_all()
    assert db.get(RemovedJob, "A1001") is None
    restored = db.scalar(select(Job).where(Job.requisition_code == "A1001"))
    assert restored is not None
    assert restored.title == "UI/UX Developer"
    assert restored.location == "Chantilly, VA"
    assert restored.status == "open"
    assert restored.closed_manually is False
    assert {row for row in db.scalars(select(Job.requisition_code)).all()} == {"A1001", "A1002"}


def test_a_deleted_job_stays_off_the_desk_when_the_listing_omits_it(db):
    db.add(RemovedJob(requisition_code="Z9001"))
    db.commit()
    state = run_crawl(db, MapFetcher({CAREERS: LISTING}), CAREERS, RecordingLLM(), RecordingEmbedder())
    assert state.last_ok is True
    assert db.get(RemovedJob, "Z9001") is not None
    assert db.scalar(select(Job).where(Job.requisition_code == "Z9001")) is None
    assert {row for row in db.scalars(select(Job.requisition_code)).all()} == {"A1001", "A1002"}
