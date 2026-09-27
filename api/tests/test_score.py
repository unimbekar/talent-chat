"""Score math from SPEC.md section 5."""

from app.core.score import covers_title, final_score, rank_pair, required_coverage, section_coverage, semantic_score, skill_score


def test_skill_score_formula():
    score, overlap = skill_score({"Java", "Python", "AWS"}, {"Java", "Python"}, {"AWS"})
    assert score == 1.0
    assert overlap == ["AWS", "Java", "Python"]

    score, overlap = skill_score({"Java"}, {"Java", "Python"}, {"AWS"})
    # must_hit = 1/2, overlap = 1, job_skills = 3
    assert score == 0.7 * 0.5 + 0.3 * (1 / 3)
    assert overlap == ["Java"]

    empty, _ = skill_score({"Java"}, set(), set())
    assert empty is None


def test_semantic_and_final():
    assert semantic_score(1) == 1
    assert semantic_score(-1) == 0
    assert semantic_score(0) == 0.5
    final, confidence = final_score(1.0, 0.5)
    assert final == 0.55 * 1.0 + 0.45 * 0.5
    assert confidence == "standard"
    final, confidence = final_score(None, 0.8)
    assert final == 0.8
    assert confidence == "low"


def test_missing_description_is_low_confidence():
    ranked = rank_pair(
        {"Java"},
        {"Java"},
        set(),
        0.2,
        description_on_file=False,
        candidate_clearance="ts_sci",
        candidate_poly="full_scope",
        job_clearance="ts_sci",
        job_poly="full_scope",
    )
    assert ranked["confidence"] == "low"
    assert ranked["skill_score"] == 1.0
    assert ranked["semantic"] == semantic_score(0.2)


def test_mandatory_and_desired_coverage():
    candidate = {"Java", "Python", "AWS"}
    mandatory = section_coverage(
        candidate,
        [
            "5+ years of Java development",
            "Python scripting for data pipelines",
            "Active TS/SCI clearance",
            "Experience with Kafka streaming",
        ],
    )
    assert mandatory["hit"] == 2
    assert mandatory["total"] == 4
    assert mandatory["pct"] == 0.5

    desired = section_coverage(candidate, ["AWS cloud architecture", "Kubernetes"])
    assert desired["hit"] == 1
    assert desired["pct"] == 0.5

    empty = section_coverage(candidate, [])
    assert empty["pct"] is None

    oracle_sql = section_coverage(
        {"Oracle SQL", "ServiceNow", "Selenium"},
        [
            "Certifications: Active Oracle Certified Professional (OCP) Database Administrator certification.",
            "Oracle Linux Administration: Proven experience serving as an Oracle Linux Systems Administrator.",
            "Oracle Exadata: Hands-on experience in Oracle Exadata administration.",
        ],
    )
    assert oracle_sql["hit"] == 0

    exadata = section_coverage(
        {"OCP", "Oracle Linux", "Exadata"},
        [
            "Active Oracle Certified Professional (OCP) Database Administrator certification.",
            "Oracle Linux Administration in enterprise environments.",
            "Oracle Exadata administration and performance optimization.",
        ],
    )
    assert exadata["hit"] == 3

    qa_lines = [
        "Proficiency in automation tools such as Selenium, Cypress, etc.",
        "Strong experience in software testing, including writing and executing test automation scripts.",
        "Ability to build test automation frameworks.",
        "Experience working with AWS, Kubernetes, Java, SpringBoot, and Angular.",
        "Excellent analytical and problem-solving skills.",
        "Strong communication and collaboration skills.",
        "Familiarity with JIRA and agile development practices.",
        "Ability to prepare test cases, test scripts, and test data.",
        "Experience with manual functional, regression, and integration testing.",
        "Knowledge of accessibility testing standards and practices.",
        "B.S. in Computer Science, Computer Engineering, or an equivalent combination of education and experience.",
    ]
    qa = section_coverage(
        {"Selenium", "Jira", "AWS", "ServiceNow"},
        qa_lines,
        (
            "Senior QA Tester. Manual functional, regression, and integration testing. "
            "Selenium automation scripts, test cases, and test data. Jira agile test planning. "
            "Communication and collaboration. Problem-solving and analytical reviews. "
            "Accessibility testing standards. B.S. Computer Science. AWS."
        ),
    )
    assert qa["pct"] is not None and qa["pct"] >= 0.5
    assert not any("Kubernetes" in line for line in qa["matched"])
    assert any("Selenium" in line for line in qa["matched"])
    assert covers_title({"Java", "Oracle", "Kubernetes"}, "Salesforce Developer") is False
    assert covers_title({"Salesforce", "Java"}, "Salesforce Developer") is True
    assert covers_title({"Kubernetes"}, "Software Quality Assurance Tester") is True

    java_only = section_coverage(
        {"Java"},
        [
            "Core Back-End Java Development: Hands-on experience developing back-end Java code (excluding JavaScript and standalone Spring Boot frameworks).",
        ],
    )
    assert java_only["hit"] == 1
    javascript_only = section_coverage(
        {"JavaScript", "Spring Boot"},
        [
            "Core Back-End Java Development: Hands-on experience developing back-end Java code (excluding JavaScript and standalone Spring Boot frameworks).",
        ],
    )
    assert javascript_only["hit"] == 0
    degree = section_coverage(
        set(),
        ["Education: Bachelor’s degree in Computer Science or an equivalent technical field."],
        "EDUCATION\nB.S., Computer Science: Delhi Institute of Technology, 1996",
    )
    assert degree["hit"] == 1
    other_degree = section_coverage(
        set(),
        ["Education: Bachelor’s degree in Mechanical Engineering."],
        "EDUCATION\nB.S., Computer Science: Delhi Institute of Technology, 1996",
    )
    assert other_degree["hit"] == 0

    search_lines = [
        "Intermediate to Expert experience with Solr or Elasticsearch.",
        "In-depth understanding of Solr/Elastic shard mechanisms and operational behavior.",
        "Tuning search engine clusters for performance, throughput, and query optimization.",
        "Constructing and optimizing complex Lucene queries.",
    ]
    elastic = section_coverage(
        {"Elasticsearch"},
        search_lines,
        "Configured an encrypted Elasticsearch cluster and indexed approximately 7 billion records.",
    )
    assert elastic["hit"] == 3
    assert not any("Lucene" in line for line in elastic["matched"])
    assert any("Lucene" in line for line in elastic["missing"])
    solr_only = section_coverage({"Solr"}, ["Experience with Solr or Elasticsearch."], "")
    assert solr_only["hit"] == 1

    gate = required_coverage(candidate, ["Java services", "Python APIs"], ["Java", "Kafka"])
    assert gate["matched"] == ["Java"]
    assert gate["missing"] == ["Kafka"]
    assert gate["pct"] == 0.5
