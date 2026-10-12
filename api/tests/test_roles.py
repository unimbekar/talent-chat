"""Recruiter accounts: sign-in, what the role can and cannot do, and account management."""

import re
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import desk_users
from app.admin.team_routes import create_account
from app.main import create_app
from app.models import AuditLog, Candidate, DeskUser, Job, Submission
from tests.fakes import RecordingEmbedder, RecordingLLM

RECRUITER = "recruiter@janus-soft.com"
RECRUITER_PASSWORD = "recruit-test-pass-1"
ADMIN_PASSWORD = "correct-horse"


def _client() -> TestClient:
    app = create_app()
    client = TestClient(app)
    client.__enter__()
    app.state.llm = RecordingLLM()
    app.state.embedder = RecordingEmbedder()
    return client


def _admin() -> TestClient:
    client = _client()
    assert client.post("/admin/login", json={"password": ADMIN_PASSWORD}).status_code == 200
    return client


def _recruiter(db, email: str = RECRUITER, password: str = RECRUITER_PASSWORD) -> TestClient:
    if db.scalar(select(DeskUser).where(DeskUser.email == email)) is None:
        create_account(db, email=email, password=password, role="recruiter", display_name="Riley Recruiter")
        db.commit()
    client = _client()
    response = client.post("/admin/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "recruiter"
    return client


def _message(response) -> str:
    detail = response.json().get("detail")
    return detail.get("message", "") if isinstance(detail, dict) else str(detail)


def _seed(db) -> tuple[Job, Candidate]:
    job = Job(requisition_code="A1001", title="UI/UX Developer", location="Chantilly, VA", status="open",
              description_text="Build interfaces.", must_have_skills=["JavaScript"], nice_to_have_skills=[])
    person = Candidate(file_sha256="alex", full_name="Alex Rivera", email="alex@example.com", status="confirmed",
                       skills=[], titles=["Developer"])
    db.add_all([job, person])
    db.commit()
    return job, person


# ---------- Sign-in ----------


def test_recruiter_signs_in_and_sees_their_role(db):
    client = _recruiter(db)
    me = client.get("/admin/session").json()
    assert me["role"] == "recruiter"
    assert me["email"] == RECRUITER
    assert me["name"] == "Riley Recruiter"
    assert me["can"] and not any(me["can"].values())
    user = db.scalar(select(DeskUser).where(DeskUser.email == RECRUITER))
    db.refresh(user)
    assert user.last_login_at is not None


def test_admin_session_reports_full_access(db):
    me = _admin().get("/admin/session").json()
    assert me["role"] == "admin"
    assert all(me["can"].values())
    assert set(me["can"]) >= {"delete", "burden", "settings", "team"}


@pytest.mark.parametrize(
    ("email", "password"),
    [
        (RECRUITER, "wrong-password-123"),
        ("nobody@janus-soft.com", RECRUITER_PASSWORD),
        (RECRUITER, ""),
    ],
)
def test_bad_recruiter_sign_ins_get_one_message(db, email, password):
    create_account(db, email=RECRUITER, password=RECRUITER_PASSWORD)
    db.commit()
    response = _client().post("/admin/login", json={"email": email, "password": password})
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password."


def test_email_is_case_insensitive(db):
    create_account(db, email=RECRUITER, password=RECRUITER_PASSWORD)
    db.commit()
    response = _client().post("/admin/login", json={"email": "  Recruiter@Janus-Soft.com ", "password": RECRUITER_PASSWORD})
    assert response.status_code == 200


def test_the_recruiter_password_does_not_open_the_admin_account(db):
    create_account(db, email=RECRUITER, password=RECRUITER_PASSWORD)
    db.commit()
    response = _client().post("/admin/login", json={"email": "admin@janus-soft.com", "password": RECRUITER_PASSWORD})
    assert response.status_code == 401


def test_logout_ends_the_session_on_the_server(db):
    client = _recruiter(db)
    cookie = client.cookies.get("admin_session")
    assert client.post("/admin/logout").status_code == 200
    replay = _client()
    replay.cookies.set("admin_session", cookie)
    assert replay.get("/admin/session").status_code == 401


# ---------- What a recruiter can do ----------


def test_recruiter_works_the_pipeline(db):
    job, person = _seed(db)
    client = _recruiter(db)
    assert client.get("/admin/overview").status_code == 200
    assert client.get("/admin/jobs").status_code == 200
    assert client.get(f"/admin/jobs/{job.requisition_code}").status_code == 200
    assert client.get("/admin/resumes").status_code == 200
    created = client.post(
        "/admin/submissions", json={"candidate_id": str(person.id), "requisition_code": "A1001", "salary_usd": 130_000}
    )
    assert created.status_code == 200
    sid = created.json()["id"]
    assert client.patch(f"/admin/submissions/{sid}", json={"stage": "interviewed", "note": "Panel on Thursday"}).status_code == 200
    comment = client.post(f"/admin/submissions/{sid}/comments", json={"body": "Strong React work."})
    assert comment.status_code == 200
    edited = client.patch(f"/admin/submissions/{sid}/comments/{comment.json()['id']}", json={"body": "Strong React and CSS."})
    assert edited.status_code == 200
    assert client.post(f"/admin/resumes/{person.id}/comments", json={"body": "Prefers hybrid."}).status_code == 200
    window = {"start": "2026-01-01T00:00:00+00:00", "end": "2027-01-01T00:00:00+00:00"}
    assert client.get("/admin/reports", params=window).status_code == 200
    assert client.get("/admin/knowledge").status_code == 200
    assert client.get("/admin/pipeline").json()["submissions"][0]["stage"] == "interviewed"


def test_audit_log_names_the_recruiter(db):
    _job, person = _seed(db)
    client = _recruiter(db)
    sid = client.post("/admin/submissions", json={"candidate_id": str(person.id), "requisition_code": "A1001"}).json()["id"]
    row = db.scalar(select(AuditLog).where(AuditLog.action == "submission_create"))
    assert row.actor == RECRUITER
    assert row.subject_id == uuid.UUID(sid)
    login = db.scalar(select(AuditLog).where(AuditLog.action == "login", AuditLog.outcome == "ok:recruiter"))
    assert login is not None and login.actor == RECRUITER


# ---------- What a recruiter cannot do ----------


def test_no_delete_route_is_open_to_a_recruiter(db):
    client = _recruiter(db)
    checked = 0
    for template, operations in create_app().openapi()["paths"].items():
        if "delete" not in operations or not template.startswith("/admin"):
            continue
        path = re.sub(r"\{[^}]+\}", str(uuid.uuid4()), template)
        response = client.delete(path, params={"tag": "any"})
        assert response.status_code == 403, f"{template} answered {response.status_code}"
        assert "cannot" in _message(response)
        checked += 1
    assert checked >= 8


@pytest.mark.parametrize(
    ("method", "path", "body", "capability"),
    [
        ("get", "/admin/burden/defaults", None, "burden"),
        ("post", "/admin/burden", {"salary": 100_000}, "burden"),
        ("put", "/admin/submissions/{sid}/burden", {"salary": 100_000}, "burden"),
        ("get", "/admin/settings", None, "settings"),
        ("put", "/admin/settings", {}, "settings"),
        ("post", "/admin/settings/models", {"tag": "x"}, "settings"),
        ("post", "/admin/jobs/A1001/close", {"note": "filled"}, "edit_jobs"),
        ("post", "/admin/jobs/A1001/reopen", None, "edit_jobs"),
        ("put", "/admin/jobs/A1001", {"title": "New"}, "edit_jobs"),
        ("post", "/admin/jobs/recrawl", None, "edit_jobs"),
        ("post", "/admin/synonyms", {"alias": "js", "canonical": "JavaScript"}, "edit_jobs"),
        ("get", "/admin/ingest/scan", None, "bulk_ingest"),
        ("post", "/admin/ingest/start", None, "bulk_ingest"),
        ("put", "/admin/knowledge/{sid}", {"title": "x", "audience": "public"}, "knowledge_edit"),
        ("get", "/admin/reports/export?start=2026-01-01T00:00:00Z&end=2027-01-01T00:00:00Z", None, "export"),
        ("get", "/admin/team", None, "team"),
        ("post", "/admin/team", {"email": "x@janus-soft.com", "password": "long-enough-123"}, "team"),
        ("patch", "/admin/team/{sid}", {"active": False}, "team"),
    ],
)
def test_admin_only_actions_tell_the_recruiter_why(db, method, path, body, capability):
    client = _recruiter(db)
    url = path.replace("{sid}", str(uuid.uuid4()))
    kwargs = {"json": body} if body is not None else {}
    response = getattr(client, method)(url, **kwargs)
    assert response.status_code == 403, response.text
    detail = response.json()["detail"]
    assert detail["capability"] == capability
    assert detail["message"].startswith("Recruiter accounts cannot")
    assert detail["message"].endswith("Ask an admin.")


def test_knowledge_upload_is_admin_only(db):
    client = _recruiter(db)
    response = client.post("/admin/knowledge", data={"title": "Handbook", "audience": "internal", "text": "Rules."})
    assert response.status_code == 403


def test_the_admin_still_passes_every_guard(db):
    _job, person = _seed(db)
    admin = _admin()
    sid = admin.post("/admin/submissions", json={"candidate_id": str(person.id), "requisition_code": "A1001"}).json()["id"]
    assert admin.get("/admin/burden/defaults").status_code == 200
    assert admin.get("/admin/settings").status_code == 200
    assert admin.get("/admin/team").status_code == 200
    assert admin.delete(f"/admin/submissions/{sid}").status_code == 200


def test_recruiters_never_see_margins(db):
    _job, person = _seed(db)
    admin = _admin()
    sid = admin.post(
        "/admin/submissions", json={"candidate_id": str(person.id), "requisition_code": "A1001", "salary_usd": 150_000}
    ).json()["id"]
    saved = admin.put(f"/admin/submissions/{sid}/burden", json={"salary": 150_000, "bill_rate": 125})
    assert saved.status_code == 200
    assert admin.get("/admin/pipeline").json()["submissions"][0]["burden_summary"]["bill_rate"] == 125

    recruiter = _recruiter(db)
    card = recruiter.get("/admin/pipeline").json()["submissions"][0]
    assert card["burden_summary"] is None
    detail = recruiter.get(f"/admin/submissions/{sid}").json()
    assert detail["burden"] is None and detail["burden_summary"] is None
    for path in (f"/admin/jobs/A1001/submissions", f"/admin/resumes/{person.id}/submissions"):
        assert all(row["burden_summary"] is None for row in recruiter.get(path).json()["submissions"])
    moved = recruiter.patch(f"/admin/submissions/{sid}", json={"stage": "interviewed"}).json()
    assert moved["burden"] is None
    # The saved calculation is untouched for the admin.
    assert admin.get(f"/admin/submissions/{sid}").json()["burden"]["saved"] is True


def test_the_assistant_stream_keeps_the_recruiter_role(db, monkeypatch):
    seen = {}

    def fake_turn(session, **kwargs):
        seen["role"] = session.info.get("role")
        seen["actor"] = session.info.get("actor")
        yield {"type": "final", "text": "ok"}

    monkeypatch.setattr("app.admin.assistant.routes.run_turn", fake_turn)
    client = _recruiter(db)
    response = client.post("/admin/assistant", json={"messages": [{"role": "user", "content": "pipeline"}]})
    assert response.status_code == 200
    assert seen == {"role": "recruiter", "actor": RECRUITER}


# ---------- Own password ----------


def test_a_recruiter_changes_only_their_own_password(db):
    client = _recruiter(db)
    wrong = client.post("/admin/password", json={"current_password": ADMIN_PASSWORD, "new_password": "brand-new-pass-99"})
    assert wrong.status_code == 400
    ok = client.post("/admin/password", json={"current_password": RECRUITER_PASSWORD, "new_password": "brand-new-pass-99"})
    assert ok.status_code == 200
    assert _client().post("/admin/login", json={"email": RECRUITER, "password": "brand-new-pass-99"}).status_code == 200
    assert _client().post("/admin/login", json={"email": RECRUITER, "password": RECRUITER_PASSWORD}).status_code == 401
    assert _client().post("/admin/login", json={"password": ADMIN_PASSWORD}).status_code == 200


# ---------- Account management ----------


def test_admin_adds_and_lists_a_recruiter(db):
    admin = _admin()
    created = admin.post("/admin/team", json={"email": " New.Person@Janus-Soft.com ", "password": "first-password-1", "display_name": "New Person"})
    assert created.status_code == 200
    body = created.json()
    assert body["email"] == "new.person@janus-soft.com" and body["role"] == "recruiter" and body["active"]
    accounts = admin.get("/admin/team").json()["accounts"]
    assert accounts[0]["builtin"] and accounts[0]["role"] == "admin"
    assert [row["email"] for row in accounts[1:]] == ["new.person@janus-soft.com"]
    signed_in = _client().post("/admin/login", json={"email": "new.person@janus-soft.com", "password": "first-password-1"})
    assert signed_in.json()["role"] == "recruiter"


@pytest.mark.parametrize(
    ("body", "status", "words"),
    [
        ({"email": "not-an-email", "password": "long-enough-123"}, 400, "full email"),
        ({"email": "a@janus-soft.com", "password": "short"}, 400, "at least 12"),
        ({"email": "admin@janus-soft.com", "password": "long-enough-123"}, 409, "built-in admin"),
        ({"email": "a@janus-soft.com", "password": "long-enough-123", "role": "owner"}, 400, "admin or recruiter"),
    ],
)
def test_bad_new_accounts_are_refused(db, body, status, words):
    response = _admin().post("/admin/team", json=body)
    assert response.status_code == status
    assert words in _message(response)


def test_duplicate_accounts_are_refused(db):
    admin = _admin()
    assert admin.post("/admin/team", json={"email": RECRUITER, "password": "long-enough-123"}).status_code == 200
    again = admin.post("/admin/team", json={"email": RECRUITER.upper(), "password": "long-enough-123"})
    assert again.status_code == 409


def test_deactivating_signs_the_recruiter_out_at_once(db):
    recruiter = _recruiter(db)
    user = db.scalar(select(DeskUser).where(DeskUser.email == RECRUITER))
    admin = _admin()
    assert admin.get("/admin/team").json()["accounts"][1]["signed_in"] is True
    off = admin.patch(f"/admin/team/{user.id}", json={"active": False})
    assert off.status_code == 200 and off.json()["active"] is False
    assert recruiter.get("/admin/pipeline").status_code == 401
    assert _client().post("/admin/login", json={"email": RECRUITER, "password": RECRUITER_PASSWORD}).status_code == 401
    assert admin.patch(f"/admin/team/{user.id}", json={"active": True}).status_code == 200
    assert _client().post("/admin/login", json={"email": RECRUITER, "password": RECRUITER_PASSWORD}).status_code == 200


def test_reset_password_and_role_change_end_old_sessions(db):
    recruiter = _recruiter(db)
    user = db.scalar(select(DeskUser).where(DeskUser.email == RECRUITER))
    admin = _admin()
    assert admin.patch(f"/admin/team/{user.id}", json={"password": "reset-by-admin-7"}).status_code == 200
    assert recruiter.get("/admin/session").status_code == 401
    assert _client().post("/admin/login", json={"email": RECRUITER, "password": RECRUITER_PASSWORD}).status_code == 401
    promoted_client = _client()
    assert promoted_client.post("/admin/login", json={"email": RECRUITER, "password": "reset-by-admin-7"}).status_code == 200
    assert admin.patch(f"/admin/team/{user.id}", json={"role": "admin"}).status_code == 200
    assert promoted_client.get("/admin/session").status_code == 401
    fresh = _client()
    assert fresh.post("/admin/login", json={"email": RECRUITER, "password": "reset-by-admin-7"}).json()["role"] == "admin"
    assert fresh.get("/admin/burden/defaults").status_code == 200
    assert admin.patch(f"/admin/team/{user.id}", json={}).status_code == 400
    assert admin.patch(f"/admin/team/{uuid.uuid4()}", json={"active": False}).status_code == 404


def test_admin_deletes_an_account(db):
    recruiter = _recruiter(db)
    user = db.scalar(select(DeskUser).where(DeskUser.email == RECRUITER))
    admin = _admin()
    assert admin.delete(f"/admin/team/{user.id}").status_code == 200
    assert recruiter.get("/admin/session").status_code == 401
    assert [row["email"] for row in admin.get("/admin/team").json()["accounts"]] == ["admin@janus-soft.com"]
    assert db.scalar(select(AuditLog).where(AuditLog.action == "team_delete")) is not None


def test_submissions_survive_when_their_recruiter_is_removed(db):
    _job, person = _seed(db)
    recruiter = _recruiter(db)
    recruiter.post("/admin/submissions", json={"candidate_id": str(person.id), "requisition_code": "A1001"})
    user = db.scalar(select(DeskUser).where(DeskUser.email == RECRUITER))
    _admin().delete(f"/admin/team/{user.id}")
    db.expire_all()
    assert db.scalar(select(Submission)) is not None


# ---------- Command line ----------


def test_cli_adds_and_resets_an_account(db, monkeypatch, capsys):
    monkeypatch.setenv("DESK_PASSWORD", "cli-password-123")
    assert desk_users.main(["add", RECRUITER, "--name", "Riley"]) == 0
    assert "add: recruiter@janus-soft.com (recruiter)" in capsys.readouterr().out
    assert desk_users.main(["add", RECRUITER]) == 1
    assert "already has an account" in capsys.readouterr().err
    assert _client().post("/admin/login", json={"email": RECRUITER, "password": "cli-password-123"}).status_code == 200
    monkeypatch.setenv("DESK_PASSWORD", "cli-password-456")
    assert desk_users.main(["reset", RECRUITER]) == 0
    assert _client().post("/admin/login", json={"email": RECRUITER, "password": "cli-password-456"}).status_code == 200
    monkeypatch.setenv("DESK_PASSWORD", "short")
    assert desk_users.main(["reset", RECRUITER]) == 1
    with pytest.raises(SystemExit):
        desk_users.main(["reset", "ghost@janus-soft.com"])
