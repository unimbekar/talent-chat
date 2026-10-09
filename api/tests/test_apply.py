"""Careers-site applications land in the pipeline only with TS/SCI and FSP."""

from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import Job, JobApplication, Submission
from tests.fakes import RecordingEmbedder, RecordingLLM

RESUME = (
    "Alex Rivera is a software engineer in Chantilly who builds services with Java and AWS. "
    "Active TOP SECRET/SCI with Full Scope Polygraph. "
    "For six years Alex designed data pipelines for a federal program."
)


def _client() -> TestClient:
    app = create_app()
    client = TestClient(app)
    client.__enter__()
    app.state.llm = RecordingLLM()
    app.state.embedder = RecordingEmbedder()
    return client


def _job(db, code="A1001", status="open") -> Job:
    job = Job(
        requisition_code=code,
        title="UI/UX Developer",
        location="Chantilly, VA",
        status=status,
        description_text="Build interfaces with JavaScript. Clearance: TS/SCI.",
        description_source="careers_page",
        must_have_skills=["JavaScript"],
        nice_to_have_skills=[],
    )
    db.add(job)
    db.commit()
    return job


def _form(**extra) -> dict:
    start = (date.today() + timedelta(days=21)).isoformat()
    base = {
        "requisition_code": "A1001",
        "full_name": "Alex Rivera",
        "email": "alex.rivera@example.com",
        "phone": "703-555-0100",
        "location": "Chantilly, VA",
        "salary_usd": "170000",
        "start_on": start,
        "years_experience": "6",
        "fsp": "yes",
        "last_fsp_on": "2024-06-01",
        "last_tssci_on": "2023-04-01",
        "note": "Happy to interview next week.",
    }
    base.update(extra)
    return base


def _file(name="alex.txt", text=RESUME):
    return {"file": (name, text.encode(), "text/plain")}


def test_open_jobs_hide_clearance_lines_and_closed_postings(db):
    _job(db)
    _job(db, code="Z9", status="closed")
    client = _client()
    try:
        response = client.get("/public/jobs")
        assert response.status_code == 200, response.text
        codes = {row["requisition_code"] for row in response.json()["jobs"]}
        assert codes == {"A1001"}
        blurb = response.json()["jobs"][0]["blurb"]
        assert "JavaScript" in blurb
        assert "TS/SCI" not in blurb
        assert "email" not in response.json()["jobs"][0]
    finally:
        client.__exit__(None, None, None)


def test_fsp_is_required_and_a_yes_is_submitted(db):
    _job(db)
    client = _client()
    try:
        refused = client.post("/public/apply", data=_form(fsp="no"), files=_file())
        assert refused.status_code == 400, refused.text
        assert "Full Scope" in refused.json()["detail"]["message"]
        assert db.query(Submission).count() == 0
        assert db.query(JobApplication).count() == 0

        accepted = client.post("/public/apply", data=_form(), files=_file())
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["created"] is True
        assert "candidate_id" not in accepted.json()
        db.expire_all()
        row = db.query(Submission).one()
        assert row.stage == "submitted"
        assert row.salary_usd == 170000
        application = db.query(JobApplication).one()
        assert application.fsp is True
        assert application.years_experience == 6
        assert row.candidate.clearance == "ts_sci"
        assert row.candidate.polygraph == "full_scope"
        assert row.candidate.email == "alex.rivera@example.com"

        again = client.post("/public/apply", data=_form(salary_usd="180000"), files=_file())
        assert again.status_code == 200, again.text
        assert again.json()["created"] is False
        db.expire_all()
        assert db.query(Submission).count() == 1
        assert db.query(Submission).one().salary_usd == 180000

        closed = client.post("/public/apply", data=_form(requisition_code="NOPE"), files=_file(name="other.txt", text=RESUME + " other"))
        assert closed.status_code == 404
    finally:
        client.__exit__(None, None, None)
