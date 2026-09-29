"""Find candidates: the model reads the question, SQL filters by skill and home state."""

import json

import pytest
from fastapi.testclient import TestClient

from app.admin.find import model_filters, rule_filters
from app.core.llm import LLMError
from app.core.structure import resume_location
from app.core.us_states import state_from_location, states_in_text
from app.main import create_app
from app.models import Candidate
from tests.fakes import RecordingEmbedder

QUESTION = "Find me all candidates having Service Now experience and they live in Maryland"


class ScriptedLLM:
    """Returns a fixed JSON reading of the question."""

    def __init__(self, reply: dict | None = None, fail: bool = False) -> None:
        self.reply = reply or {}
        self.fail = fail
        self.prompts: list[dict] = []

    def complete(self, *, system: str, user: str, temperature: float, json_mode: bool) -> str:
        self.prompts.append({"system": system, "user": user, "json_mode": json_mode})
        if self.fail:
            raise LLMError("model endpoint stopped")
        return json.dumps(self.reply)


@pytest.mark.parametrize(
    ("location", "state"),
    [
        ("Largo, MD", "MD"),
        ("Fort Washington, MD", "MD"),
        ("Baltimore, Maryland 21201", "MD"),
        ("Washington, DC", "DC"),
        ("Chantilly, VA", "VA"),
        ("Maryland", "MD"),
        ("PAT, IP", None),
        ("SSBI, TS", None),
        ("Maria DB, MS", None),
        ("Lotus Notes, MS", None),
        ("Active Directory, MS", None),
        ("Jackson, MS 39201", "MS"),
        ("Jackson, Mississippi", "MS"),
        ("Storch Ct Lanham, MD", None),
        ("City, NJ", None),
        ("Jersey City, NJ", "NJ"),
        ("CACI, VA", None),
        ("American Inter Continental University, VA", None),
        ("Maryland, DC", None),
        ("", None),
        (None, None),
    ],
)
def test_state_from_location(location, state):
    assert state_from_location(location) == state


def test_states_in_text_reads_names_and_codes_but_not_english_words():
    assert states_in_text(QUESTION) == ["MD"]
    assert states_in_text("Java people in VA or MD") == ["VA", "MD"]
    assert states_in_text("West Virginia only") == ["WV"]
    assert states_in_text("anyone in DC") == ["DC"]
    assert states_in_text("Java OR Python, ME too") == []
    assert states_in_text("people who live in OR") == ["OR"]


def test_resume_location_prefers_header_and_rejects_non_places():
    text = "Jane Doe\nLargo, MD 20774\njane@example.com\n\nExperience\nEngineer at CACI, Chantilly, VA\n"
    assert resume_location(text) == "Largo, MD"
    junk = "Pat Smith\nSkills: PAT, IP routing\nSystems Administrator Oracle Reston, VA\n"
    assert resume_location(junk) == "Reston, VA"
    assert resume_location("Summary\nSSBI, TS clearance holder") is None
    assert resume_location("Nana Kojo\n12 Storch Ct Lanham, MD 20706\n") == "Lanham, MD"
    assert resume_location("Lee Ray\nSkills: Active Directory, MS Office\n") is None
    body_only = "Sam Lee\n" + "\n".join(f"Duty line {n}" for n in range(20)) + "\nClient site: Suitland, MD\n"
    assert resume_location(body_only) is None


def test_candidate_state_follows_location():
    row = Candidate(file_sha256="x", location="Largo, MD")
    assert row.state == "MD"
    row.location = "PAT, IP"
    assert row.state is None


def test_rule_filters_treat_service_now_as_a_skill_not_a_role():
    filters = rule_filters(QUESTION)
    assert filters.skills == ["ServiceNow"]
    assert filters.states == ["MD"]
    assert filters.categories == []
    assert rule_filters("Show me all Software Testers.").categories == ["Software Tester"]


def test_model_filters_drop_what_the_question_did_not_ask():
    llm = ScriptedLLM(
        {"skills": ["ServiceNow", "ITIL"], "states": ["MD", "VA"], "roles": ["ServiceNow Developer"], "keywords": []}
    )
    filters = model_filters(QUESTION, llm)
    assert filters.parser == "llm"
    assert filters.skills == ["ServiceNow"]
    assert filters.states == ["MD"]
    assert filters.categories == []
    assert llm.prompts[0]["json_mode"] is True
    assert "Maryland" in llm.prompts[0]["user"]


def test_model_filters_understand_outside_and_city_names():
    outside = model_filters(
        "Java developers outside Virginia",
        ScriptedLLM({"skills": ["Java"], "exclude_states": ["VA"], "roles": ["Software Engineer"]}),
    )
    assert outside.states == []
    assert outside.exclude_states == ["VA"]
    assert outside.skills == ["Java"]

    near = model_filters(
        "ServiceNow admins near Baltimore",
        ScriptedLLM({"skills": ["ServiceNow"], "states": ["MD"], "cities": [{"city": "Baltimore", "state": "MD"}]}),
    )
    assert near.states == ["MD"]

    invented = model_filters(
        "ServiceNow admins",
        ScriptedLLM({"skills": ["ServiceNow"], "states": ["MD"], "cities": [{"city": "Baltimore", "state": "MD"}]}),
    )
    assert invented.states == []


def test_model_filters_keep_a_named_state_the_model_left_out():
    filters = model_filters(QUESTION, ScriptedLLM({"skills": ["ServiceNow"], "states": []}))
    assert filters.states == ["MD"]


def _seed(db) -> None:
    db.add_all(
        [
            Candidate(
                file_sha256="md-snow",
                full_name="Maria Lopez",
                location="Largo, MD",
                status="pending_review",
                skills=[{"name": "Java", "years": None}],
                titles=["Systems Engineer"],
                redacted_text="Maria Lopez\nLargo, MD\nBuilt ServiceNow ITSM workflows for five years.",
            ),
            Candidate(
                file_sha256="va-snow",
                full_name="Victor Adams",
                location="Herndon, VA",
                status="pending_review",
                skills=[{"name": "ServiceNow", "years": 4}],
                titles=["Service Now Engineer"],
                redacted_text="Victor Adams\nHerndon, VA\nServiceNow developer supporting Fort Meade, Maryland.",
            ),
            Candidate(
                file_sha256="md-java",
                full_name="Mona Park",
                location="Elkridge, MD",
                status="pending_review",
                skills=[{"name": "Java", "years": 6}],
                titles=["Software Engineer"],
                redacted_text="Mona Park\nElkridge, MD\nJava services and Spring.",
            ),
            Candidate(
                file_sha256="junk-snow",
                full_name="Pat Unknown",
                location="PAT, IP",
                status="pending_review",
                skills=[{"name": "ServiceNow", "years": None}],
                titles=[],
                redacted_text="Pat Unknown\nServiceNow administrator.",
            ),
        ]
    )
    db.commit()


def _ask(llm, message: str) -> dict:
    app = create_app()
    with TestClient(app) as client:
        app.state.llm = llm
        app.state.embedder = RecordingEmbedder()
        login = client.post("/admin/login", json={"password": "correct-horse"})
        assert login.status_code == 200, login.text
        response = client.post("/admin/candidates/ask", json={"message": message})
        assert response.status_code == 200, response.text
        return response.json()


def test_ask_returns_only_maryland_servicenow_people(db):
    _seed(db)
    body = _ask(ScriptedLLM({"skills": ["ServiceNow"], "states": ["MD"]}), QUESTION)
    assert [person["full_name"] for person in body["candidates"]] == ["Maria Lopez"]
    assert body["filters"]["parser"] == "llm"
    assert body["filters"]["skills"] == ["ServiceNow"]
    assert body["filters"]["states"] == [{"code": "MD", "name": "Maryland"}]
    assert body["unknown_location"] == 1
    assert "Maryland" in body["answer"]


def test_ask_still_filters_by_state_when_the_model_is_down(db):
    _seed(db)
    body = _ask(ScriptedLLM(fail=True), QUESTION)
    assert [person["full_name"] for person in body["candidates"]] == ["Maria Lopez"]
    assert body["filters"]["parser"] == "rules"


def test_ask_outside_a_state_excludes_it_and_unknown_homes(db):
    _seed(db)
    body = _ask(ScriptedLLM({"skills": ["ServiceNow"], "exclude_states": ["MD"]}), "ServiceNow people outside Maryland")
    assert [person["full_name"] for person in body["candidates"]] == ["Victor Adams"]


def test_ask_role_question_still_uses_categories(db):
    _seed(db)
    body = _ask(ScriptedLLM({"roles": ["Software Engineer"]}), "Show me all Software Engineers.")
    assert [person["full_name"] for person in body["candidates"]] == ["Mona Park"]
