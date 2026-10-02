from app.core.labor import categories_for_question, labor_categories, role_conflict


def test_avery_headline_is_software_tester():
    text = (
        "Avery Saunders, Senior IT & QA Tester\n"
        "EXPERIENCE SUMMARY: IT & QA Project Manager / Senior Tester"
    )
    assert labor_categories("Avery_Saunders_Resume.docx", text) == ["Software Tester"]


def test_kate_headline_includes_cybersecurity():
    text = (
        "Kate Dribki\n"
        "Experienced Data Engineer. Cyber Threat Intelligence – Security Engineer."
    )
    cats = labor_categories("Kate Dribki-DataScientist.docx", text)
    assert "CyberSecurity Engineer" in cats
    assert "Data Scientist" in cats


def test_cyber_resume_is_not_a_data_scientist_match():
    text = (
        "SHASHI DABIR\n"
        "A Cyber Security Analyst/Architect/Engineer with penetration testing, "
        "forensic analysis, and cloud security architectures."
    )
    assert role_conflict("DabirJune2025.docx", text, ["Cyber Risk Manager"], "Data Scientist") == ["Data Scientist"]
    assert role_conflict("ShashiDabirResume_Latest.docx", text, ["CyberSecurity Engineer"], "Data Scientist") == ["Data Scientist"]
    both = "Experienced Data Engineer. Cyber Threat Intelligence – Security Engineer."
    assert role_conflict("Kate-DataScientist.docx", both, [], "Data Scientist") == []


def test_question_finds_tester_and_cyber_categories():
    assert categories_for_question("Show me all Software Testers.") == ["Software Tester"]
    assert categories_for_question("Find all Cybersecurity Engineers.") == ["CyberSecurity Engineer"]
    assert "AI Engineer" in categories_for_question("Show me candidates with Machine Learning experience.")
