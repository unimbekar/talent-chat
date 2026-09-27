"""SSN redaction and skill synonyms."""

from app.core.redact import contains_ssn, redact_ssn
from app.core.skills import find_canonicals, normalize_skill_list


def test_redact_dashed_and_labeled_ssn():
    text = "SSN 123-45-6789 and social security number 987654321. Phone 703-555-0100."
    redacted = redact_ssn(text)
    assert "123-45-6789" not in redacted
    assert "987654321" not in redacted
    assert "[REDACTED]" in redacted
    assert "703-555-0100" in redacted
    assert not contains_ssn(redacted)


def test_word_boundaries_and_multi_canonical():
    assert find_canonicals("PySpark pipelines") == ["Python", "Spark"] or set(find_canonicals("PySpark pipelines")) == {
        "Python",
        "Spark",
    }
    assert "Java" not in find_canonicals("springboard training")
    assert "JavaScript" not in find_canonicals("many nodes in the graph")
    assert "AWS" not in find_canonicals("use S30 storage")
    assert "Java" in find_canonicals("Spring Boot and Java")
    assert "AWS" in find_canonicals("Amazon Web Services and S3")
    skills = normalize_skill_list(
        ["TS/SCI", "Clearance: Active Top Secret", "PySpark", "underwater basket"]
    )
    assert "Python" in skills and "Spark" in skills
    assert all("secret" not in skill and "ts/sci" not in skill for skill in skills)
    assert "underwater basket" in skills
    assert "DevOps" not in find_canonicals("Kubernetes and Docker")
    assert find_canonicals("Kubernetes") == ["Kubernetes"]
    assert find_canonicals("CI/CD pipelines") == ["DevOps"]


def test_resume_skills_keep_tools_and_drop_prose():
    from app.core.skills import tools_and_languages
    from app.core.structure import resume_facts

    text = """Alex Rivera
Skills
Python, Terraform, EKS, LangChain
Professional Experience
Apr 2025 – Present
Built notification delivery and task delegation with Java.
"""
    names = {skill["name"] for skill in resume_facts(text)["skills"]}
    assert {"Python", "Terraform", "EKS", "LangChain", "Java"} <= names
    assert all("delivery" not in name.lower() and "experience" not in name.lower() for name in names)
    assert tools_and_languages("integrated langsmith for llm tracing") == ["LangSmith"]
    assert tools_and_languages("professional experience") == []
