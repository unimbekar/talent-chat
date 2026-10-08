"""Submission pipeline: stages, salary, comments, and history."""

import psycopg
import pytest
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


def _login(client: TestClient) -> None:
    assert client.post("/admin/login", json={"password": "correct-horse"}).status_code == 200


def _message(response) -> str:
    detail = response.json().get("detail")
    if isinstance(detail, dict):
        return detail.get("message") or ""
    return detail or ""


def _seed(db) -> tuple[Job, Candidate, Candidate]:
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
    other = Job(
        requisition_code="L4001",
        title="Cyber Security Engineer",
        location="Herndon, VA",
        status="open",
        description_text="Watch the network.",
        description_source="careers_page",
        must_have_skills=["Security"],
        nice_to_have_skills=[],
    )
    alex = Candidate(
        file_sha256="alex",
        full_name="Alex Rivera",
        email="alex@example.com",
        location="Chantilly, VA",
        status="confirmed",
        skills=[],
        titles=["Developer"],
    )
    sam = Candidate(
        file_sha256="sam",
        full_name="Sam Roe",
        email="sam@example.com",
        location="Reston, VA",
        status="confirmed",
        skills=[],
        titles=["Analyst"],
    )
    db.add_all([job, other, alex, sam])
    db.commit()
    return job, alex, sam


def test_submission_requires_sign_in(db):
    _job, alex, _sam = _seed(db)
    client = _client()
    response = client.post(
        "/admin/submissions",
        json={"candidate_id": str(alex.id), "requisition_code": "A1001"},
    )
    assert response.status_code == 401


def test_create_list_stage_salary_and_history(db):
    _job, alex, sam = _seed(db)
    client = _client()
    try:
        _login(client)
        created = client.post(
            "/admin/submissions",
            json={
                "candidate_id": str(alex.id),
                "requisition_code": "A1001",
                "note": "Sent to the hiring manager",
            },
        )
        assert created.status_code == 200, created.text
        body = created.json()
        assert body["stage"] == "submitted"
        assert body["candidate"]["full_name"] == "Alex Rivera"
        assert body["job"]["requisition_code"] == "A1001"
        assert body["events"][0]["kind"] == "created"
        assert body["events"][0]["body"] == "Sent to the hiring manager"
        submission_id = body["id"]

        again = client.post(
            "/admin/submissions",
            json={"candidate_id": str(alex.id), "requisition_code": "A1001"},
        )
        assert again.status_code == 409
        assert again.json()["detail"]["submission_id"] == submission_id

        missing = client.post(
            "/admin/submissions",
            json={"candidate_id": str(alex.id), "requisition_code": "NOPE"},
        )
        assert missing.status_code == 404

        bad_stage = client.patch(f"/admin/submissions/{submission_id}", json={"stage": "hired"})
        assert bad_stage.status_code == 400
        assert "hired" not in _message(bad_stage) or "Stage must be" in _message(bad_stage)

        salary = client.patch(
            f"/admin/submissions/{submission_id}",
            json={"stage": "salary", "salary_usd": 165000, "salary_note": "W2", "note": "Asked for 165"},
        )
        assert salary.status_code == 200, salary.text
        assert salary.json()["salary_usd"] == 165000
        assert salary.json()["stage"] == "salary"
        assert [event["kind"] for event in salary.json()["events"]] == ["created", "stage"]

        too_high = client.patch(f"/admin/submissions/{submission_id}", json={"salary_usd": 9_000_000})
        assert too_high.status_code == 400

        interviewed = client.patch(f"/admin/submissions/{submission_id}", json={"stage": "interviewed"})
        assert interviewed.status_code == 200
        rejected = client.patch(
            f"/admin/submissions/{submission_id}",
            json={"stage": "rejected", "note": "Client chose another résumé"},
        )
        assert rejected.status_code == 200
        assert rejected.json()["terminal"] is True
        kinds = [event["to_stage"] for event in rejected.json()["events"]]
        assert kinds == ["submitted", "salary", "interviewed", "rejected"]

        reopened = client.patch(f"/admin/submissions/{submission_id}", json={"stage": "submitted", "note": "Trying again"})
        assert reopened.status_code == 200
        assert reopened.json()["stage"] == "submitted"
        assert len(reopened.json()["events"]) == 5

        second = client.post(
            "/admin/submissions",
            json={"candidate_id": str(sam.id), "requisition_code": "A1001", "stage": "selected"},
        )
        assert second.status_code == 200
        other_job = client.post(
            "/admin/submissions",
            json={"candidate_id": str(alex.id), "requisition_code": "L4001"},
        )
        assert other_job.status_code == 200

        by_job = client.get("/admin/jobs/A1001/submissions")
        assert by_job.status_code == 200
        names = {row["candidate"]["full_name"] for row in by_job.json()["submissions"]}
        assert names == {"Alex Rivera", "Sam Roe"}

        history = client.get(f"/admin/resumes/{alex.id}/submissions")
        assert history.status_code == 200
        codes = {row["job"]["requisition_code"] for row in history.json()["submissions"]}
        assert codes == {"A1001", "L4001"}

        board = client.get("/admin/pipeline")
        assert board.status_code == 200
        assert board.json()["active"] >= 2
        closed = client.get("/admin/pipeline?scope=closed")
        assert closed.status_code == 200
        assert closed.json()["submissions"] == []

        jobs = client.get("/admin/jobs").json()["jobs"]
        a1001 = next(job for job in jobs if job["requisition_code"] == "A1001")
        assert a1001["submission_count"] == 2
    finally:
        client.__exit__(None, None, None)


def test_comments_on_submission_and_candidate(db):
    _job, alex, _sam = _seed(db)
    client = _client()
    try:
        _login(client)
        created = client.post(
            "/admin/submissions",
            json={"candidate_id": str(alex.id), "requisition_code": "A1001"},
        )
        submission_id = created.json()["id"]
        comment = client.post(
            f"/admin/submissions/{submission_id}/comments",
            json={"body": "  Panel is Tuesday at 2.  "},
        )
        assert comment.status_code == 200, comment.text
        assert comment.json()["body"] == "Panel is Tuesday at 2."
        comment_id = comment.json()["id"]
        edited = client.patch(
            f"/admin/submissions/{submission_id}/comments/{comment_id}",
            json={"body": "Panel moved to Wednesday."},
        )
        assert edited.status_code == 200
        assert edited.json()["edited"] is True
        empty = client.post(f"/admin/submissions/{submission_id}/comments", json={"body": "   "})
        assert empty.status_code == 400
        assert client.delete(f"/admin/submissions/{submission_id}/comments/{comment_id}").status_code == 200
        detail = client.get(f"/admin/submissions/{submission_id}")
        assert detail.json()["comments"] == []

        person = client.post(f"/admin/resumes/{alex.id}/comments", json={"body": "Prefers remote two days a week."})
        assert person.status_code == 200, person.text
        person_id = person.json()["id"]
        listed = client.get(f"/admin/resumes/{alex.id}/comments")
        assert listed.json()["comments"][0]["body"] == "Prefers remote two days a week."
        assert client.patch(
            f"/admin/resumes/{alex.id}/comments/{person_id}",
            json={"body": "Prefers remote."},
        ).status_code == 200
        assert client.delete(f"/admin/resumes/{alex.id}/comments/{person_id}").status_code == 200
        assert client.get(f"/admin/resumes/{alex.id}/comments").json()["comments"] == []

        assert client.delete(f"/admin/submissions/{submission_id}").status_code == 200
        assert client.get(f"/admin/submissions/{submission_id}").status_code == 404
        assert client.get(f"/admin/resumes/{alex.id}/submissions").json()["submissions"] == []
    finally:
        client.__exit__(None, None, None)


def test_public_role_cannot_read_submissions(_database):
    connection = psycopg.connect("postgresql://app_public:public@127.0.0.1:5432/talent_test")
    for table in ("submissions", "submission_events", "submission_comments", "candidate_comments"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute(f"SELECT * FROM {table}")
        connection.rollback()
    connection.close()


def test_original_resume_file_and_candidate_pipeline_filter(db, tmp_path):
    job, alex, sam = _seed(db)
    pdf = tmp_path / "alex"
    pdf.write_bytes(b"%PDF-1.4 alex")
    alex.original_path = str(pdf)
    alex.original_filename = "Alex Rivera résumé.pdf"
    sam.original_path = str(tmp_path / "gone")
    db.commit()
    client = _client()
    try:
        assert client.get(f"/admin/resumes/{alex.id}/file").status_code == 401
        _login(client)
        opened = client.get(f"/admin/resumes/{alex.id}/file")
        assert opened.status_code == 200
        assert opened.content == b"%PDF-1.4 alex"
        assert opened.headers["content-type"] == "application/pdf"
        assert opened.headers["content-disposition"].startswith("inline;")
        assert "filename*=UTF-8''Alex%20Rivera%20r%C3%A9sum%C3%A9.pdf" in opened.headers["content-disposition"]
        assert client.get(f"/admin/resumes/{sam.id}/file").status_code == 404

        assert client.post("/admin/submissions", json={"candidate_id": str(alex.id), "requisition_code": "A1001"}).status_code == 200
        board = client.get(f"/admin/pipeline?scope=all&candidate_id={alex.id}").json()
        assert [(row["job"]["requisition_code"], row["stage_label"]) for row in board["submissions"]] == [("A1001", "Submitted")]
        assert client.get(f"/admin/pipeline?scope=all&candidate_id={sam.id}").json()["submissions"] == []
    finally:
        client.__exit__(None, None, None)
