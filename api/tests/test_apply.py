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
    job = _job(db)
    job.external_req = "STAR 2330-04"
    job.source_line = "G2002 - Data Scientist - Mclean VA (STAR 2330-04)"
    db.commit()
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
        row = response.json()["jobs"][0]
        assert "email" not in row
        assert "external_req" not in row
        assert "funding" not in row
        assert "source_line" not in row
        assert "STAR" not in response.text
    finally:
        client.__exit__(None, None, None)


def test_job_detail_shows_the_careers_posting_and_not_the_internal_description(db):
    job = _job(db)
    job.careers_description_text = (
        "Career\n\nCareer\n\nUI/UX Developer - Chantilly VA\n\nUI/UX Developer - Chantilly VA\n\n"
        "Role Overview\n\nBuild interfaces with JavaScript.\n\nClearance: TS/SCI with Full Scope Polygraph."
    )
    job.external_req = "MOON1136-08"
    job.description_text = "Internal: client is paying 190k, do not share."
    job.description_source = "admin"
    db.add(Job(requisition_code="Z9", title="Gone", status="closed", careers_description_text="Old."))
    db.commit()
    client = _client()
    try:
        response = client.get("/public/jobs/A1001")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["paragraphs"] == [
            "Role Overview",
            "Build interfaces with JavaScript.",
            "Clearance: TS/SCI with Full Scope Polygraph.",
        ]
        assert "Internal" not in response.text
        assert "external_req" not in body
        assert "funding" not in body
        assert "MOON" not in response.text
        assert body["description_note"] is None

        assert client.get("/public/jobs/Z9").status_code == 404
        assert client.get("/public/jobs/NOPE").status_code == 404
    finally:
        client.__exit__(None, None, None)


class _FakeSMTP:
    sent: list = []
    fail = False

    def __init__(self, host, port, timeout=None):
        self.host = host

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        pass

    def login(self, user, password):
        if _FakeSMTP.fail:
            raise OSError("535 bad credentials")

    def send_message(self, message):
        _FakeSMTP.sent.append(message)


def test_application_emails_the_recruiters(db, monkeypatch):
    import app.notify as notify
    from app.config import get_settings

    settings = get_settings()
    for key, value in {
        "notify_to": "jobs@janus-soft.com, lead@janus-soft.com",
        "notify_from": "Recruiter Desk <desk@janus-soft.com>",
        "smtp_username": "desk@janus-soft.com",
        "smtp_password": "app-password",
        "desk_url": "https://desk.example.net/",
    }.items():
        monkeypatch.setattr(settings, key, value)
    monkeypatch.setattr(notify.smtplib, "SMTP", _FakeSMTP)
    _FakeSMTP.sent = []
    _FakeSMTP.fail = False
    _job(db)
    client = _client()
    try:
        accepted = client.post("/public/apply", data=_form(), files=_file())
        assert accepted.status_code == 200, accepted.text
        assert "notice" not in accepted.json()
        assert len(_FakeSMTP.sent) == 1
        message = _FakeSMTP.sent[0]
        assert message["Subject"] == "New application: Alex Rivera for A1001 UI/UX Developer"
        assert message["To"] == "jobs@janus-soft.com, lead@janus-soft.com"
        assert message["Reply-To"] == "alex.rivera@example.com"
        body = message.get_body(("plain",)).get_content()
        submission = db.query(Submission).one()
        assert f"https://desk.example.net/admin/submissions/{submission.id}" in body
        assert "$170,000" in body and "703-555-0100" in body and "Happy to interview" in body
        assert not [part for part in message.iter_attachments()]

        _FakeSMTP.fail = True
        again = client.post("/public/apply", data=_form(salary_usd="175000"), files=_file())
        assert again.status_code == 200, again.text
        assert len(_FakeSMTP.sent) == 1

        _FakeSMTP.fail = False
        monkeypatch.setattr(settings, "smtp_password", "")
        client.post("/public/apply", data=_form(salary_usd="176000"), files=_file())
        assert len(_FakeSMTP.sent) == 1
    finally:
        client.__exit__(None, None, None)


def test_application_pushes_to_subscribed_devices(db, monkeypatch):
    import json

    import app.push as push
    from pywebpush import WebPushException

    pushed: list[tuple[str, dict, dict]] = []
    gone: set[str] = set()

    def fake_webpush(info, data, vapid_private_key, vapid_claims, ttl, timeout):
        if info["endpoint"] in gone:
            raise WebPushException("gone", response=type("R", (), {"status_code": 410})())
        pushed.append((info["endpoint"], json.loads(data), vapid_claims))

    monkeypatch.setattr(push, "webpush", fake_webpush)
    _job(db)
    client = _client()
    phone = "https://fcm.googleapis.com/fcm/send/abc123"
    iphone = "https://web.push.apple.com/QGt1-xyz"
    keys = {"p256dh": "B" + "x" * 86, "auth": "y" * 22}
    try:
        assert client.get("/admin/push/key").status_code == 401
        assert client.post("/admin/login", json={"password": "correct-horse"}).status_code == 200
        key = client.get("/admin/push/key").json()
        assert len(key["public_key"]) == 87 and key["devices"] == 0
        assert client.get("/admin/push/key").json()["public_key"] == key["public_key"]

        bad = client.post("/admin/push/subscribe", json={"endpoint": "https://evil.example.com/x", "keys": keys})
        assert bad.status_code == 400
        for endpoint in (phone, iphone, phone):
            assert client.post("/admin/push/subscribe", json={"endpoint": endpoint, "keys": keys}).status_code == 200
        assert client.get("/admin/push/key").json()["devices"] == 2

        accepted = client.post("/public/apply", data=_form(), files=_file())
        assert accepted.status_code == 200, accepted.text
        assert {endpoint for endpoint, _, _ in pushed} == {phone, iphone}
        payload = pushed[0][1]
        submission = db.query(Submission).one()
        assert payload["title"] == "New application: A1001"
        assert payload["body"] == "Alex Rivera · UI/UX Developer · Chantilly, VA"
        assert payload["url"] == f"/admin/submissions/{submission.id}"
        assert pushed[0][2]["sub"].startswith("mailto:")

        gone.add(iphone)
        pushed.clear()
        assert client.post("/admin/push/test").json() == {"sent": 1}
        assert client.get("/admin/push/key").json()["devices"] == 1

        assert client.post("/admin/push/unsubscribe", json={"endpoint": phone}).status_code == 200
        assert client.get("/admin/push/key").json()["devices"] == 0
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
