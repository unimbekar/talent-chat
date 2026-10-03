"""Public questions about a named tool use the requirement lines."""

from types import SimpleNamespace

from app.core.locations import Location
from app.public.query import parse_query
from app.public.requirements import evidence_line, line_requires


def _job(**kwargs):
    defaults = {
        "title": "Software Engineer",
        "description_text": "",
        "must_have_skills": [],
        "nice_to_have_skills": [],
        "skill_quotes": {},
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_withing_is_read_as_a_radius_around_bethesda():
    parsed = parse_query("find jobs that are withing 30 miles of Bethesda MD", [], ())
    assert parsed.near_place == "Bethesda, MD"
    assert parsed.near_miles == 30
    assert parsed.fts == ""


def test_miles_of_a_place_sets_the_radius_without_the_word_within():
    parsed = parse_query("find jobs 30 miles of Bethesda MD", [], ())
    assert parsed.near_place == "Bethesda, MD"
    assert parsed.near_miles == 30
    assert parsed.fts == ""


def test_city_and_tool_typos_still_filter():
    chantilly = Location("Chantilly, VA", ("chantilly", "chantilly va"), 38.89, -77.43)
    city = parse_query("jobs in Chantily", [], (chantilly,))
    assert city.city == "Chantilly, VA"
    assert city.fts == ""
    tool = parse_query("jobs that require pyhton", [], ())
    assert "Python" in tool.phrases
    assert tool.required_only is True


def test_ordinary_words_are_not_rewritten_into_search_terms():
    parsed = parse_query("string and sensor jobs", [], ())
    assert "Spring" not in parsed.phrases
    assert parsed.senior_only is False


def test_machine_learning_is_a_tool_phrase_not_a_keyword_search():
    parsed = parse_query("Machine Learning Jobs", [], ())
    assert parsed.phrases == ["Machine Learning"]
    assert parsed.skills == []
    assert parsed.fts == ""
    quoted = _job(
        title="Software / AI Architect",
        skill_quotes={
            "must": [
                "Emerging Technologies & AI: Demonstrated experience with AI, Machine Learning, or other cutting-edge technologies.",
            ]
        },
        description_text="Lead full-stack engineering for mission systems.",
    )
    abbreviated = _job(
        title="Data Scientist",
        description_text="Candidate should be expert in understanding AI/ML Algorithms",
        skill_quotes={
            "must": [
                "AI/ML & Multimedia Forensics: Demonstrated experience evaluating next-generation AI/ML capabilities.",
            ]
        },
    )
    unrelated = _job(description_text="Build Java services on AWS.", must_have_skills=["Java", "AWS"])
    assert "Machine Learning" in (evidence_line(quoted, ["Machine Learning"], required_only=False) or "")
    assert "AI/ML" in (evidence_line(abbreviated, ["Machine Learning"], required_only=False) or "")
    assert evidence_line(unrelated, ["Machine Learning"], required_only=False) is None


def test_spring_boot_question_stays_specific():
    parsed = parse_query("what all jobs require SPring Boot", [], ())
    assert "Spring Boot" in parsed.phrases
    assert "Java" not in parsed.skills
    assert parsed.fts == ""
    assert parsed.required_only is True


def test_exclusion_does_not_count_as_a_requirement():
    excluded = "Core Java patterns (explicitly excluding Spring Boot)."
    also = "Hands-on experience developing back-end Java code (excluding JavaScript and standalone Spring Boot frameworks)."
    required = "Demonstrated expertise in multi-language full-stack development, with proven hands-on experience using Java (Spring Framework) and Python."
    variants = ["Spring Boot", "SpringBoot", "Spring Framework", "Spring"]
    assert line_requires(excluded, variants) is False
    assert line_requires(also, variants) is False
    assert line_requires(required, variants) is True
    assert line_requires("applications built with Java, SpringBoot, and Angular", variants) is True


def test_open_spring_framework_line_is_evidence_and_an_exclusion_is_not():
    spring = _job(
        skill_quotes={
            "must": [
                "Full-Stack Development: Demonstrated expertise using Java (Spring Framework) and Python.",
            ]
        },
        must_have_skills=["Java", "Python"],
        description_text="Lead full-stack engineering for mission systems.",
    )
    excluded = _job(
        description_text="Quartz Job Scheduling using pure Java patterns (explicitly excluding Spring Boot).",
        must_have_skills=["Java"],
        skill_quotes={"must": ["explicitly excluding Spring Boot"]},
    )
    assert "Spring Framework" in (evidence_line(spring, ["Spring Boot"], required_only=True) or "")
    assert evidence_line(excluded, ["Spring Boot"], required_only=True) is None
