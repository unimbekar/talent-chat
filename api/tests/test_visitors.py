"""Careers-site visitor counting and the admin visitors summary."""

from datetime import date, datetime, timezone
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError

from app.admin.visitors import summary
from app.db import public_session
from app.main import create_app
from app.models import Candidate, Job, JobApplication, SiteVisit, Submission
from app.public import visits
from app.public.visits import device_of, is_bot, normal_path, source_of

CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
NY = "America/New_York"


@pytest.fixture(autouse=True)
def _fresh_limit():
    visits.reset_rate_limit()
    yield
    visits.reset_rate_limit()


def _client() -> TestClient:
    client = TestClient(create_app())
    client.__enter__()
    return client


def _admin() -> TestClient:
    client = _client()
    assert client.post("/admin/login", json={"password": "correct-horse"}).status_code == 200
    return client


def _job(db, code: str = "A1001", title: str = "UI/UX Developer") -> Job:
    job = Job(requisition_code=code, title=title, location="Chantilly, VA", status="open", description_text="Build.",
              must_have_skills=[], nice_to_have_skills=[])
    db.add(job)
    db.commit()
    return job


def _visit(db, visitor: uuid.UUID, at: str, kind: str = "page", path: str = "/jobs", source: str = "direct", device: str = "desktop"):
    db.add(SiteVisit(visitor=visitor, at=datetime.fromisoformat(at), kind=kind, path=path, source=source, device=device))


def _application(db, job: Job, at: str) -> None:
    person = Candidate(file_sha256=uuid.uuid4().hex, full_name="Casey Applicant", email="casey@example.com", status="confirmed",
                       skills=[], titles=[])
    db.add(person)
    db.flush()
    submission = Submission(candidate_id=person.id, job_id=job.id)
    db.add(submission)
    db.flush()
    db.add(JobApplication(submission_id=submission.id, candidate_id=person.id, job_id=job.id, full_name="Casey Applicant",
                          email="casey@example.com", phone="703-555-0199", location="McLean, VA", salary_usd=150000,
                          start_on=date(2026, 4, 1), years_experience=8, fsp=True, created_at=datetime.fromisoformat(at)))


# ---------- Cleaning what the browser sends ----------


@pytest.mark.parametrize(
    ("kind", "raw", "expected"),
    [
        ("page", "/jobs", "/jobs"),
        ("page", "/jobs/", "/jobs"),
        ("page", "/JOBS/Benefits?utm_source=email#top", "/jobs/benefits"),
        ("page", "/admin/login", None),
        ("page", "/jobs/../admin", None),
        ("page", "https://evil.example/jobs", None),
        ("posting", "A1001", "A1001"),
        ("apply", "G2003", "G2003"),
        ("posting", "<script>", None),
        ("posting", "A" * 41, None),
    ],
)
def test_paths_are_ours_or_dropped(kind, raw, expected):
    assert normal_path(kind, raw) == expected


@pytest.mark.parametrize(
    ("referrer", "campaign", "expected"),
    [
        (None, "Email", "email"),
        ("https://www.linkedin.com/feed/", "linkedin_post", "linkedin_post"),
        ("https://www.linkedin.com/feed/", None, "linkedin"),
        ("https://lnkd.in/abc", None, "linkedin"),
        ("https://mail.google.com/mail/u/0/", None, "email"),
        ("https://outlook.office.com/mail/", None, "email"),
        ("https://www.google.com/", None, "google"),
        ("https://www.google.co.uk/", None, "google"),
        ("https://t.co/xyz", None, "x"),
        ("https://www.indeed.com/viewjob", None, "indeed"),
        ("https://janus-soft.com/careers", None, "janus-soft.com"),
        ("https://jobs.janus-soft.com/jobs", None, "direct"),
        ("javascript:alert(1)", None, "direct"),
        ("", None, "direct"),
        ("https://news.example.org/story?id=7", "<b>bad</b>", "news.example.org"),
    ],
)
def test_sources_are_short_names(referrer, campaign, expected):
    assert source_of(referrer, campaign, {"jobs.janus-soft.com"}) == expected


@pytest.mark.parametrize(
    ("agent", "expected"),
    [
        (CHROME, "desktop"),
        (IPHONE, "mobile"),
        ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/128.0 Mobile Safari/537.36", "mobile"),
        ("Mozilla/5.0 (Linux; Android 13; SM-X710) AppleWebKit/537.36 Chrome/128.0 Safari/537.36", "tablet"),
        ("Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148", "tablet"),
    ],
)
def test_device_type(agent, expected):
    assert device_of(agent) == expected


@pytest.mark.parametrize(
    "agent",
    ["", None, "Googlebot/2.1 (+http://www.google.com/bot.html)", "curl/8.5", "Mozilla/5.0 HeadlessChrome/128.0",
     "facebookexternalhit/1.1", "python-requests/2.32", "WhatsApp/2.23"],
)
def test_bots_are_not_counted(agent):
    assert is_bot(agent)


def test_a_real_browser_is_not_a_bot():
    assert not is_bot(CHROME)
    assert not is_bot(IPHONE)


# ---------- The beacon ----------


def test_beacon_records_a_page_without_identifying_data(db):
    client = _client()
    visitor = uuid.uuid4()
    response = client.post(
        "/public/visit",
        json={"visitor": str(visitor), "kind": "page", "path": "/jobs/benefits", "referrer": "https://www.linkedin.com/feed/"},
        headers={"user-agent": IPHONE},
    )
    assert response.status_code == 204
    row = db.scalar(select(SiteVisit))
    assert (row.visitor, row.kind, row.path, row.source, row.device) == (visitor, "page", "/jobs/benefits", "linkedin", "mobile")
    columns = {column.name for column in SiteVisit.__table__.columns}
    assert columns == {"id", "at", "visitor", "kind", "path", "source", "device"}


def test_beacon_prefers_the_campaign_tag(db):
    _client().post("/public/visit", json={"visitor": str(uuid.uuid4()), "kind": "page", "path": "/jobs", "campaign": "Email",
                                          "referrer": "https://mail.google.com/"}, headers={"user-agent": CHROME})
    assert db.scalar(select(SiteVisit.source)) == "email"


def test_beacon_ignores_bots_strange_paths_and_unknown_jobs(db):
    _job(db)
    client = _client()
    visitor = str(uuid.uuid4())
    sent = [
        ({"visitor": visitor, "kind": "page", "path": "/jobs"}, "Googlebot/2.1"),
        ({"visitor": visitor, "kind": "page", "path": "/admin/login"}, CHROME),
        ({"visitor": visitor, "kind": "posting", "path": "Z9999"}, CHROME),
        ({"visitor": visitor, "kind": "posting", "path": "A1001"}, CHROME),
        ({"visitor": visitor, "kind": "apply", "path": "A1001"}, CHROME),
    ]
    for body, agent in sent:
        assert client.post("/public/visit", json=body, headers={"user-agent": agent}).status_code == 204
    kept = sorted(tuple(row) for row in db.execute(select(SiteVisit.kind, SiteVisit.path)).all())
    assert kept == [("apply", "A1001"), ("posting", "A1001")]


def test_a_quick_repeat_counts_once_but_a_later_view_counts_again(db):
    client = _client()
    visitor = uuid.uuid4()
    body = {"visitor": str(visitor), "kind": "page", "path": "/jobs"}
    for _ in range(3):
        client.post("/public/visit", json=body, headers={"user-agent": CHROME})
    client.post("/public/visit", json={**body, "path": "/jobs/benefits"}, headers={"user-agent": CHROME})
    client.post("/public/visit", json={**body, "visitor": str(uuid.uuid4())}, headers={"user-agent": CHROME})
    assert db.scalar(select(text("count(*)")).select_from(SiteVisit)) == 3

    db.execute(text("UPDATE site_visits SET at = at - interval '1 minute'"))
    db.commit()
    client.post("/public/visit", json=body, headers={"user-agent": CHROME})
    assert db.scalar(select(text("count(*)")).select_from(SiteVisit).where(SiteVisit.visitor == visitor)) == 3


@pytest.mark.parametrize(
    "body",
    [
        {"visitor": "not-a-uuid", "kind": "page", "path": "/jobs"},
        {"visitor": str(uuid.uuid4()), "kind": "click", "path": "/jobs"},
        {"visitor": str(uuid.uuid4()), "kind": "page", "path": ""},
        {"visitor": str(uuid.uuid4()), "kind": "page", "path": "/jobs" + "x" * 300},
    ],
)
def test_beacon_rejects_malformed_bodies(db, body):
    assert _client().post("/public/visit", json=body, headers={"user-agent": CHROME}).status_code == 422
    assert db.scalar(select(SiteVisit)) is None


def test_beacon_is_rate_limited_quietly(db, monkeypatch):
    monkeypatch.setattr(visits, "HOURLY_LIMIT", 3)
    client = _client()
    for _ in range(5):
        response = client.post("/public/visit", json={"visitor": str(uuid.uuid4()), "kind": "page", "path": "/jobs"},
                               headers={"user-agent": CHROME})
        assert response.status_code == 204
    assert db.scalar(select(text("count(*)")).select_from(SiteVisit)) == 3


def test_the_public_database_role_cannot_read_visits(db):
    session = public_session()
    try:
        with pytest.raises(ProgrammingError):
            session.execute(select(SiteVisit)).all()
    finally:
        session.rollback()
        session.close()


# ---------- The admin summary ----------


def _seed_week(db):
    """Three local days in New York, March 10 to 12, 2026, with visitors before and around them."""
    job = _job(db)
    old, fresh, phone, earlier = (uuid.uuid4() for _ in range(4))
    _visit(db, old, "2026-03-01T15:00:00+00:00")  # first seen long before the range
    _visit(db, earlier, "2026-03-08T15:00:00+00:00")  # only in the previous period
    _visit(db, old, "2026-03-10T14:00:00+00:00")
    _visit(db, fresh, "2026-03-10T16:00:00+00:00", source="email")
    _visit(db, fresh, "2026-03-10T16:01:00+00:00", path="/jobs/benefits", source="email")
    _visit(db, fresh, "2026-03-10T16:02:00+00:00", kind="posting", path="A1001", source="email")
    _visit(db, fresh, "2026-03-10T16:03:00+00:00", kind="apply", path="A1001", source="email")
    # 03:30 UTC on the 11th is 23:30 on the 10th in New York.
    _visit(db, old, "2026-03-11T03:30:00+00:00", path="/jobs/benefits")
    _visit(db, phone, "2026-03-12T15:50:00+00:00", source="linkedin", device="mobile")
    _visit(db, phone, "2026-03-12T15:52:00+00:00", kind="posting", path="A1001", source="linkedin", device="mobile")
    _application(db, job, "2026-03-11T15:00:00+00:00")
    db.commit()


def _range(db, now: datetime | None = None) -> dict:
    return summary(
        db,
        datetime(2026, 3, 10, 4, tzinfo=timezone.utc),
        datetime(2026, 3, 13, 4, tzinfo=timezone.utc),
        NY,
        now=now or datetime(2026, 3, 12, 16, tzinfo=timezone.utc),
    )


def test_visitors_per_day_follow_the_local_calendar(db):
    _seed_week(db)
    days = _range(db)["days"]
    assert [day["date"] for day in days] == ["2026-03-10", "2026-03-11", "2026-03-12"]
    assert [day["visitors"] for day in days] == [2, 0, 1]
    assert [day["views"] for day in days] == [4, 0, 1]
    assert [day["postings"] for day in days] == [1, 0, 1]
    assert [day["new"] for day in days] == [1, 0, 1]
    assert [day["applications"] for day in days] == [0, 1, 0]


def test_total_visitors_grow_with_each_new_browser(db):
    _seed_week(db)
    report = _range(db)
    assert [day["total"] for day in report["days"]] == [3, 3, 4]
    assert report["all_time"] == {"visitors": 4, "views": 7, "since": "2026-03-01"}


def test_range_totals_new_returning_and_change(db):
    _seed_week(db)
    totals = _range(db)["range"]
    assert totals["visitors"] == 3
    assert totals["new"] == 2
    assert totals["returning"] == 1
    assert totals["views"] == 5
    assert totals["views_per_visitor"] == 1.7
    assert totals["daily_average"] == 1.0
    assert totals["peak"] == {"date": "2026-03-10", "visitors": 2}
    assert totals["applications"] == 1
    assert totals["visitors_change"] == 200.0
    assert totals["views_change"] == 400.0


def test_today_and_the_last_fifteen_minutes(db):
    _seed_week(db)
    report = _range(db, now=datetime(2026, 3, 12, 16, 0, tzinfo=timezone.utc))
    assert report["today"] == {"visitors": 1, "views": 1}
    assert report["live"] == 1
    assert _range(db, now=datetime(2026, 3, 12, 17, 0, tzinfo=timezone.utc))["live"] == 0


def test_funnel_pages_postings_sources_and_devices(db):
    _seed_week(db)
    report = _range(db)
    assert [(step["label"], step["count"]) for step in report["funnel"]] == [
        ("Visited the site", 3),
        ("Opened a posting", 2),
        ("Started an application", 1),
    ]
    assert report["range"]["applications"] == 1
    assert report["pages"] == [
        {"key": "/jobs", "label": "Open jobs", "views": 3, "visitors": 3},
        {"key": "/jobs/benefits", "label": "Benefits", "views": 2, "visitors": 2},
    ]
    assert report["postings"] == [{"code": "A1001", "title": "UI/UX Developer", "views": 2, "visitors": 2, "applying": 1}]
    assert {item["label"]: item["count"] for item in report["sources"]} == {"Direct or bookmark": 1, "Email": 1, "LinkedIn": 1}
    assert {item["label"]: item["count"] for item in report["devices"]} == {"Desktop": 2, "Phone": 1}


def test_an_empty_site_still_draws_every_day(db):
    report = _range(db)
    assert [day["visitors"] for day in report["days"]] == [0, 0, 0]
    assert report["range"]["peak"] is None
    assert report["range"]["visitors_change"] is None
    assert report["all_time"] == {"visitors": 0, "views": 0, "since": None}
    assert report["funnel"][0]["count"] == 0


def test_daylight_saving_week_has_one_bar_per_day(db):
    # US clocks moved forward on March 8, 2026; that day is 23 hours long in New York.
    report = summary(db, datetime(2026, 3, 7, 5, tzinfo=timezone.utc), datetime(2026, 3, 10, 4, tzinfo=timezone.utc), NY)
    assert [day["date"] for day in report["days"]] == ["2026-03-07", "2026-03-08", "2026-03-09"]


# ---------- The admin endpoint ----------


def test_endpoint_returns_the_summary_for_admins(db):
    _seed_week(db)
    response = _admin().get("/admin/visitors", params={"start": "2026-03-10T04:00:00Z", "end": "2026-03-13T04:00:00Z", "tz": NY})
    assert response.status_code == 200
    body = response.json()
    assert body["range"]["visitors"] == 3
    assert body["timezone"] == NY


def test_endpoint_needs_a_session(db):
    response = _client().get("/admin/visitors", params={"start": "2026-03-10T04:00:00Z", "end": "2026-03-13T04:00:00Z"})
    assert response.status_code == 401


@pytest.mark.parametrize(
    ("params", "words"),
    [
        ({"start": "2026-03-13T04:00:00Z", "end": "2026-03-10T04:00:00Z"}, "after the start"),
        ({"start": "2025-01-01T00:00:00Z", "end": "2026-03-10T04:00:00Z"}, "a year or less"),
        ({"start": "2026-03-10T04:00:00", "end": "2026-03-13T04:00:00"}, "with a timezone"),
        ({"start": "2026-03-10T04:00:00Z", "end": "2026-03-13T04:00:00Z", "tz": "Mars/Olympus"}, "not recognized"),
    ],
)
def test_endpoint_explains_a_bad_range(db, params, words):
    response = _admin().get("/admin/visitors", params=params)
    assert response.status_code == 400
    assert words in response.json()["detail"]["message"]
