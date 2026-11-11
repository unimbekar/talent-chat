"""The desk shows the candidate posting and saves profiles a recruiter pasted from LinkedIn."""

from fastapi.testclient import TestClient

from app.core.posting import form_linkedin_query, linkedin_role_terms
from app.main import create_app
from app.models import Job


def test_linkedin_query_keeps_ts_sci_and_full_scope_poly():
    job = Job(
        requisition_code="G2004",
        title="Software Engineer - McLean VA",
        location="McLean, VA",
        status="open",
        must_have_skills=[
            "Java",
            "Core Java & EE Development: Expert knowledge of Core Java that is far too long to paste into LinkedIn.",
            "Clearance",
        ],
        nice_to_have_skills=[],
    )
    terms = linkedin_role_terms(job)
    assert terms == ["Software Engineer", "Java", "Core Java & EE Development"]
    query = form_linkedin_query(terms, job.location or "", "all")
    assert "Expert knowledge" not in query
    assert "Clearance" not in query
    assert query.startswith('("TS/SCI" OR "TS SCI" OR "Top Secret/SCI" OR "Top Secret SCI")')
    assert '("Full Scope Polygraph" OR "Full Scope Poly" OR FSP)' in query
    wider = form_linkedin_query(["Java", "Python"], "", "any")
    assert "(Java OR Python)" in wider
    assert wider.startswith('("TS/SCI"')


def test_desk_job_shows_the_candidate_posting_and_saves_a_linkedin_profile(db):
    db.add(
        Job(
            requisition_code="G2004",
            title="Software Engineer",
            location="McLean, VA",
            status="open",
            description_text="Internal note for the desk only.",
            careers_description_text="Career\n\nSoftware Engineer G2004\n\nWe build Java services.\n\nRequired skills\n\nJava",
            description_source="careers_page",
            must_have_skills=["Java"],
            nice_to_have_skills=[],
        )
    )
    db.commit()
    app = create_app()
    with TestClient(app) as client:
        assert client.post("/admin/login", json={"password": "correct-horse"}).status_code == 200
        job = client.get("/admin/jobs/G2004")
        assert job.status_code == 200, job.text
        body = job.json()
        assert "We build Java services." in body["posting_paragraphs"]
        assert "Required skills" in body["posting_paragraphs"]
        assert "Internal note" not in " ".join(body["posting_paragraphs"])
        assert body["linkedin"]["query"].startswith('("TS/SCI"')
        assert "Full Scope Polygraph" in body["linkedin"]["query"]
        assert "FSP" in body["linkedin"]["query"]
        assert '"Software Engineer" AND Java AND McLean' in body["linkedin"]["query"]
        assert "TS%2FSCI" in body["linkedin"]["recruiter_url"]
        assert "Full%20Scope%20Polygraph" in body["linkedin"]["recruiter_url"]
        assert "linkedin.com/talent/search" in body["linkedin"]["recruiter_url"]

        other_site = client.post(
            "/admin/jobs/G2004/linkedin",
            json={"full_name": "Ada Lovelace", "profile_url": "https://example.com/ada"},
        )
        assert other_site.status_code == 400
        company = client.post(
            "/admin/jobs/G2004/linkedin",
            json={"full_name": "Ada Lovelace", "profile_url": "https://www.linkedin.com/company/example"},
        )
        assert company.status_code == 400

        saved = client.post(
            "/admin/jobs/G2004/linkedin",
            json={
                "full_name": "Ada Lovelace",
                "profile_url": "https://www.linkedin.com/in/ada",
                "headline": "Engineer",
                "note": "Found in Recruiter.",
            },
        )
        assert saved.status_code == 200, saved.text
        again = client.post(
            "/admin/jobs/G2004/linkedin",
            json={
                "full_name": "Ada Lovelace",
                "profile_url": "https://www.linkedin.com/in/ada",
                "note": "Spoke on Tuesday.",
            },
        )
        assert again.status_code == 200
        listed = client.get("/admin/jobs/G2004/linkedin")
        leads = listed.json()["leads"]
        assert len(leads) == 1
        assert leads[0]["note"] == "Spoke on Tuesday."
        assert "linkedin.com/search/results/people" in listed.json()["people_url"]

        removed = client.delete(f"/admin/jobs/G2004/linkedin/{leads[0]['id']}")
        assert removed.status_code == 200
        assert client.get("/admin/jobs/G2004/linkedin").json()["leads"] == []
