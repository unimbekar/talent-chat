"""Date-range reports: ingest, submissions, clearance, salary, and outcomes."""

from datetime import datetime, timedelta, timezone
from io import BytesIO
from zipfile import ZipFile

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import Candidate, Job, Submission, SubmissionEvent
from tests.fakes import RecordingEmbedder, RecordingLLM

START = datetime(2026, 10, 1, tzinfo=timezone.utc)
END = datetime(2026, 10, 8, tzinfo=timezone.utc)
INSIDE = datetime(2026, 10, 7, 15, tzinfo=timezone.utc)
OUTSIDE = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _client() -> TestClient:
    app = create_app()
    client = TestClient(app)
    client.__enter__()
    app.state.llm = RecordingLLM()
    app.state.embedder = RecordingEmbedder()
    return client


def _login(client: TestClient) -> None:
    assert client.post("/admin/login", json={"password": "correct-horse"}).status_code == 200


def _params(**extra) -> dict:
    base = {"start": START.isoformat(), "end": END.isoformat(), "tz": "UTC"}
    base.update(extra)
    return base


def _seed(db):
    job = Job(
        requisition_code="A1001",
        title="UI/UX Developer",
        location="Chantilly, VA",
        status="open",
        description_text="Build interfaces.",
        description_source="careers_page",
        must_have_skills=["JavaScript"],
        nice_to_have_skills=[],
    )
    alex = Candidate(
        file_sha256="alex-report",
        full_name="Alex Rivera",
        email="alex@example.com",
        location="Chantilly, VA",
        clearance="ts_sci",
        polygraph="full_scope",
        status="confirmed",
        skills=[],
        titles=["Developer"],
        created_at=INSIDE,
    )
    sam = Candidate(
        file_sha256="sam-report",
        full_name="Sam Roe",
        email="sam@example.com",
        location="Reston, VA",
        clearance="secret",
        polygraph="ci",
        status="confirmed",
        skills=[],
        titles=["Analyst"],
        created_at=INSIDE,
    )
    old = Candidate(
        file_sha256="old-report",
        full_name="=Old Name",
        email="old@example.com",
        clearance="ts_sci",
        polygraph="full_scope",
        status="confirmed",
        skills=[],
        titles=[],
        created_at=OUTSIDE,
    )
    quiet = Candidate(
        file_sha256="quiet-report",
        full_name="Quiet Quinn",
        email="quiet@example.com",
        status="pending_review",
        skills=[],
        titles=[],
        created_at=INSIDE - timedelta(days=1),
    )
    db.add_all([job, alex, sam, old, quiet])
    db.commit()
    high = Submission(
        candidate_id=alex.id,
        job_id=job.id,
        stage="interviewed",
        salary_usd=180000,
        salary_note="W2",
        created_at=INSIDE,
        updated_at=INSIDE,
    )
    low = Submission(
        candidate_id=sam.id,
        job_id=job.id,
        stage="submitted",
        salary_usd=165000,
        created_at=INSIDE,
        updated_at=INSIDE,
    )
    db.add_all([high, low])
    db.commit()
    db.add(
        SubmissionEvent(
            submission_id=high.id,
            kind="stage",
            from_stage="submitted",
            to_stage="rejected",
            at=INSIDE,
        )
    )
    db.add(
        SubmissionEvent(
            submission_id=high.id,
            kind="stage",
            from_stage="rejected",
            to_stage="selected",
            at=OUTSIDE,
        )
    )
    db.commit()
    return alex, sam, old, quiet, high


def test_report_requires_sign_in(db):
    _seed(db)
    client = _client()
    assert client.get("/admin/reports", params=_params()).status_code == 401


def test_range_ingest_submit_clearance_salary_and_outcomes(db):
    alex, sam, old, quiet, _high = _seed(db)
    client = _client()
    try:
        _login(client)
        response = client.get(
            "/admin/reports",
            params=_params(poly="full_scope", salary_gt=165000, salary_scope="range", clearance_scope="range"),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        ingested = {row["full_name"] for row in body["ingested"]["candidates"]}
        assert ingested == {"Alex Rivera", "Sam Roe", "Quiet Quinn"}
        assert body["ingested"]["total"] == 3
        assert body["ingested"]["also_submitted"] == 2
        assert sum(point["count"] for point in body["ingested"]["by_day"]) == 3
        assert any(point["count"] == 0 for point in body["ingested"]["by_day"])

        submitted = {row["candidate"]["full_name"] for row in body["submitted"]["rows"]}
        assert submitted == {"Alex Rivera", "Sam Roe"}
        assert body["submitted"]["total"] == 2
        assert body["submitted"]["by_job"][0]["requisition_code"] == "A1001"
        assert body["submitted"]["by_job"][0]["count"] == 2

        assert body["outcomes"]["rejected"] == 1
        assert body["outcomes"]["selected"] == 0
        assert body["outcomes"]["rows"][0]["candidate"]["full_name"] == "Alex Rivera"
        assert all(row["at"][:10] != "2026-09-01" for row in body["outcomes"]["rows"])

        roster = {row["full_name"] for row in body["clearance"]["candidates"]}
        assert roster == {"Alex Rivera"}
        assert old.full_name not in roster
        assert sam.full_name not in roster

        whole = client.get("/admin/reports", params=_params(poly="full_scope", clearance_scope="all", salary_gt=165000, salary_scope="all"))
        assert whole.status_code == 200
        names = {row["full_name"] for row in whole.json()["clearance"]["candidates"]}
        assert names == {"Alex Rivera", "=Old Name"}

        above = {row["candidate"]["full_name"] for row in body["salary"]["rows"]}
        assert above == {"Alex Rivera"}
        assert 165000 not in {row["salary_usd"] for row in body["salary"]["rows"]}
        assert body["salary"]["with_salary"] == 2

        backwards = client.get("/admin/reports", params=_params(start=END.isoformat(), end=START.isoformat()))
        assert backwards.status_code == 400
        assert client.get("/admin/reports", params=_params(tz="Not/AZone")).status_code == 400
        assert client.get("/admin/reports", params=_params(poly="nope")).status_code == 400
    finally:
        client.__exit__(None, None, None)


def test_exports_csv_and_xlsx(db):
    _seed(db)
    client = _client()
    try:
        _login(client)
        csv_response = client.get("/admin/reports/export", params=_params(format="csv", sheet="clearance", poly="full_scope", clearance_scope="all"))
        assert csv_response.status_code == 200, csv_response.text
        text = csv_response.content.decode("utf-8-sig")
        assert text.startswith("Name,Email")
        assert "'=Old Name" in text
        assert "Alex Rivera" in text
        assert "Sam Roe" not in text

        refused = client.get("/admin/reports/export", params=_params(format="csv", sheet="all"))
        assert refused.status_code == 400

        book = client.get("/admin/reports/export", params=_params(format="xlsx", sheet="all", salary_gt=100000))
        assert book.status_code == 200
        assert book.headers["content-type"].startswith("application/vnd.openxmlformats")
        archive = ZipFile(BytesIO(book.content))
        names = set(archive.namelist())
        assert "xl/workbook.xml" in names
        workbook = archive.read("xl/workbook.xml").decode("utf-8")
        assert "ingested" in workbook
        assert "salary" in workbook
        sheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        assert "Ingested" in sheet
    finally:
        client.__exit__(None, None, None)
