"""Years of experience estimated from a résumé for the review page and submission sheet."""

from datetime import date
from io import BytesIO
from zipfile import ZipFile

from fastapi.testclient import TestClient

from app.admin.submission_sheet import excel_years, submission_workbook
from app.core.experience import annotate, stated_years
from app.main import create_app
from app.models import Candidate, Job
from tests.fakes import RecordingEmbedder, RecordingLLM

TODAY = date(2026, 11, 2)

RESUME = """Software Engineer
Alex Rivera
alex@example.com

Summary
Software engineer with 8 years of Java and 4 years of AWS.

Experience
Acme
January 2018 - Present
Built Java services for a federal program.

Northwind
March 2022 - Present
AWS cloud architecture and Kubernetes clusters.
"""

JAVA = "5+ years of Java development"
AWS = "Experience with AWS"
BOTH = "Experience working with AWS and Java"
EITHER = "Proficiency in automation tools such as Selenium, Cypress, etc."
DEGREE = "B.S. in Computer Science, or an equivalent combination of education and experience."
TESTING = "Experience with manual functional, regression, and integration testing."


def _years(line: str, text: str = RESUME) -> dict:
    return annotate(text, [line], TODAY)[0]


def test_stated_figure_and_role_dates_keep_the_longer_stretch():
    java = _years(JAVA)
    assert java["years"] == 9
    assert java["basis"] == "roles"
    assert java["label"] == "9 yrs"
    aws = _years(AWS)
    assert aws["years"] == 4.5
    assert aws["label"] == "4.5 yrs"


def test_word_numbers_parenthetical_years_and_since():
    assert stated_years("Six years of Python.", "Python", TODAY) == 6
    assert stated_years("Java (8+ years) in production services.", "Java", TODAY) == 8
    since = stated_years("Java since 2018 on the same program.", "Java", TODAY)
    assert since is not None and since >= 8


def test_a_nearby_career_length_does_not_attach_to_a_skill():
    text = "15 years of experience.\n\nSkills: Java, Python"
    assert stated_years(text, "Java", TODAY) is None
    assert _years(JAVA, text)["years"] is None


def test_overlapping_roles_are_counted_once():
    text = """Software Engineer
Alpha
2016 - 2020
Java services
Beta
2018 - 2019
Java APIs
"""
    found = _years(JAVA, text)
    assert found["years"] == 4
    assert found["basis"] == "roles"


def test_every_required_tool_limits_the_line_and_a_gap_stays_visible():
    both = _years(BOTH)
    assert both["years"] == 4.5
    assert "shorter" in both["detail"]
    partial = _years("Experience working with AWS, Kubernetes, and Terraform.")
    assert partial["years"] is None
    assert partial["basis"] == "partial"
    assert "AWS" in partial["label"]
    assert "Terraform not stated" in partial["label"]


def test_an_example_list_uses_the_longer_tool():
    text = """Software Engineer
Studio
January 2018 - Present
Selenium automation.
Lab
January 2024 - Present
Cypress end to end tests.
"""
    found = _years(EITHER, text)
    assert found["years"] == 9
    assert "longer" in found["detail"]


def test_degree_and_undated_prose_stay_honest():
    degree = _years(DEGREE)
    assert degree["years"] is None
    assert degree["label"] == "Degree"
    undated = _years(TESTING, "Software tester. Manual functional, regression, and integration testing.")
    assert undated["years"] is None
    dated = _years(
        TESTING,
        """Software Engineer
January 2021 - Present
Manual functional, regression, and integration testing for federal systems.
""",
    )
    assert dated["years"] is not None and dated["years"] >= 5
    assert dated["basis"] == "roles"


def test_numeric_dates_and_present():
    text = """Software Engineer
01/2020 - Present
Python services.
"""
    found = _years("Python scripting for data pipelines", text)
    assert found["basis"] == "roles"
    assert found["years"] == 7


def test_workbook_puts_years_on_met_requirements_and_leaves_the_rest_blank():
    review = {
        "candidate": {"full_name": "Alex Rivera", "email": "alex@example.com", "location": "Reston, VA"},
        "mandatory_pct": 1,
        "desired_pct": 0.5,
        "meets_bar": True,
        "mandatory_experience": [_years(JAVA), _years(AWS)],
        "desired_experience": [_years("Kubernetes")],
    }
    payload = submission_workbook([review], [JAVA, AWS, "Active TS/SCI clearance"], ["Kubernetes"])
    with ZipFile(BytesIO(payload)) as book:
        requirements = book.read("xl/worksheets/sheet2.xml").decode("utf-8")
    assert "5+ years of Java development" in requirements
    assert ">9<" in requirements
    assert ">4.5<" in requirements
    assert "Kubernetes" in requirements
    assert excel_years(None) == ""
    assert excel_years(_years(JAVA)) == 9


def _client() -> TestClient:
    app = create_app()
    client = TestClient(app)
    client.__enter__()
    app.state.llm = RecordingLLM()
    app.state.embedder = RecordingEmbedder()
    return client


def test_review_and_sheet_share_the_same_years(db):
    job = Job(
        requisition_code="J1001",
        title="Software Engineer",
        location="Reston, VA",
        status="open",
        description_text="Build Java services.",
        description_source="admin",
        must_have_skills=["Java", "AWS"],
        nice_to_have_skills=["Kubernetes"],
        skill_quotes={"must": [JAVA, AWS], "nice": ["Kubernetes"]},
    )
    person = Candidate(
        file_sha256="alex-years",
        full_name="Alex Rivera",
        email="alex@example.com",
        location="Reston, VA",
        original_filename="Alex-Rivera.pdf",
        status="confirmed",
        skills=[],
        titles=["Software Engineer"],
        redacted_text=RESUME,
    )
    db.add_all([job, person])
    db.commit()
    client = _client()
    assert client.post("/admin/login", json={"password": "correct-horse"}).status_code == 200
    review = client.get("/admin/review", params={"code": "J1001", "candidate_id": str(person.id)})
    assert review.status_code == 200
    body = review.json()
    java = next(item for item in body["mandatory_experience"] if "Java" in item["line"])
    assert java["years"] == 9
    sheet = client.get("/admin/review/sheet", params={"code": "J1001", "candidates": str(person.id)})
    assert sheet.status_code == 200
    assert sheet.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert "submission-J1001.xlsx" in sheet.headers["content-disposition"]
    with ZipFile(BytesIO(sheet.content)) as book:
        requirements = book.read("xl/worksheets/sheet2.xml").decode("utf-8")
    assert ">9<" in requirements
