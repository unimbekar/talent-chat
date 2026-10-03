from app.core.structure import resume_facts


def test_cached_resume_facts_are_not_shared_between_callers():
    text = "Pat Example\nReston, VA 20190\nSkills: Python, Java, AWS"
    first = resume_facts(text)
    first["skills"].clear()
    first["full_name"] = "Changed"
    second = resume_facts(text)
    assert second["full_name"] == "Pat Example"
    assert {item["name"] for item in second["skills"]} >= {"Python", "Java"}
