"""Phase 1 crawl, chat, and résumé acceptance checks."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.crawler import MapFetcher, run_crawl
from app.main import create_app
from app.models import Job
from app.public.refusal import REFUSAL_TEXT
from tests.fakes import RecordingEmbedder, RecordingLLM

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "careers"
CAREERS = "https://www.janus-soft.com/career"
RESUME = (
    "Alex Rivera is a software engineer in Chantilly who builds services with Java, Python, and AWS. "
    "Active TOP SECRET/SCI with Full Scope Polygraph. "
    "TOP SECRET. "
    "For six years Alex designed data pipelines, reviewed pull requests, and supported production releases "
    "for a federal analytics program. The work included APIs, tests, and on-call response."
)
SSN_RESUME = RESUME + " SSN 123-45-6789 and social security number 987654321."


def _client(llm: RecordingLLM, embedder: RecordingEmbedder) -> tuple[TestClient, object]:
    app = create_app()
    client = TestClient(app)
    client.__enter__()
    app.state.llm = llm
    app.state.embedder = embedder
    return client, app


def _login(client: TestClient) -> None:
    response = client.post("/admin/login", json={"password": "correct-horse"})
    assert response.status_code == 200, response.text


def _fixture_fetcher() -> MapFetcher:
    listing = (FIXTURES / "career_2026-09-27.html").read_text(encoding="utf-8", errors="replace")
    pages = {CAREERS: listing}
    for path in FIXTURES.glob("job_*.html"):
        number = path.stem.split("_", 1)[1]
        pages[f"https://janus-soft.com/jobs/{number}"] = path.read_text(encoding="utf-8", errors="replace")
    return MapFetcher(pages)


def test_fixture_crawl_reload_close_and_guard(db):
    llm = RecordingLLM()
    embedder = RecordingEmbedder()
    state = run_crawl(db, _fixture_fetcher(), CAREERS, llm, embedder)
    assert state.last_ok is True
    jobs = db.query(Job).all()
    codes = {job.requisition_code for job in jobs}
    assert len(jobs) == 19
    assert len(codes) == 19
    assert all((job.description_text or "").strip() for job in jobs)
    a1001 = next(job for job in jobs if job.requisition_code == "A1001")
    assert a1001.title == "UI/UX Developer"
    assert a1001.location == "Chantilly, VA"
    assert "Mid Level Software Engineer" not in (a1001.title or "")
    calls_after_first = len(embedder.documents)
    run_crawl(db, _fixture_fetcher(), CAREERS, llm, embedder)
    assert db.query(Job).count() == 19
    assert len(embedder.documents) == calls_after_first

    listing = (FIXTURES / "career_2026-09-27.html").read_text(encoding="utf-8", errors="replace")
    removed = listing.replace("L4001 - Cyber Security Engineer - Herndon VA", "")
    pages = dict(_fixture_fetcher().pages)
    pages[CAREERS] = removed
    run_crawl(db, MapFetcher(pages), CAREERS, llm, embedder)
    closed = db.query(Job).filter(Job.requisition_code == "L4001").one()
    assert closed.status == "closed"
    assert db.query(Job).filter(Job.status == "open").count() == 18

    added = removed.replace(
        "</body>",
        '<p><a href="https://janus-soft.com/jobs/9001">Z9001 - Example Analyst - Ashburn VA</a></p></body>',
    )
    detail = """
    <html><body>
    <h1>Example Analyst - Ashburn VA</h1>
    <p>Job Description</p>
    <p>Build Java services on AWS for an Ashburn program with a long enough description to store.</p>
    <p>Mandatory Skills</p>
    <ul><li>Java: five years of Java services.</li></ul>
    <p>Google Sites</p><p>Report abuse</p>
    </body></html>
    """
    pages[CAREERS] = added
    pages["https://janus-soft.com/jobs/9001"] = detail
    run_crawl(db, MapFetcher(pages), CAREERS, llm, embedder)
    opened = db.query(Job).filter(Job.requisition_code == "Z9001").one()
    assert opened.status == "open"
    assert opened.location == "Ashburn, VA"

    before = {job.requisition_code: job.status for job in db.query(Job).all()}
    empty = MapFetcher({CAREERS: "<html><body><p>Open Positions</p></body></html>"})
    state = run_crawl(db, empty, CAREERS, llm, embedder)
    assert state.last_ok is False
    assert "0 rows" in (state.last_error or "")
    after = {job.requisition_code: job.status for job in db.query(Job).all()}
    assert after == before

    failed = MapFetcher({}, error=RuntimeError("timed out"))
    state = run_crawl(db, failed, CAREERS, llm, embedder)
    assert state.last_ok is False
    assert "Listing fetch failed" in (state.last_error or "")
    after_error = {job.requisition_code: job.status for job in db.query(Job).all()}
    assert after_error == before

    client, _app = _client(llm, embedder)
    try:
        _login(client)
        screen = client.get("/admin/jobs")
        assert screen.status_code == 200
        assert "Listing fetch failed" in screen.text
    finally:
        client.__exit__(None, None, None)


def test_public_chat_filters_refusal_and_llm_down(db):
    db.add_all(
        [
            Job(
                requisition_code="A1001",
                title="UI/UX Developer",
                location="Chantilly, VA",
                status="open",
                description_text="Design interfaces in Chantilly. No salary is listed.",
                description_source="careers_page",
                must_have_skills=["JavaScript"],
                nice_to_have_skills=[],
            ),
            Job(
                requisition_code="A1003",
                title="Software Developer",
                location="Herndon, VA",
                status="open",
                description_text="Build Java and AWS services with Python on Amazon Web Services.",
                description_source="careers_page",
                must_have_skills=["Java", "Python"],
                nice_to_have_skills=["AWS"],
            ),
            Job(
                requisition_code="N3001",
                title="Network Engineer",
                location="McLean, VA",
                status="open",
                description_text="",
                description_source="none",
                must_have_skills=["Java", "AWS"],
                nice_to_have_skills=[],
            ),
            Job(
                requisition_code="G2002",
                title="Data Scientist",
                location="McLean, VA",
                status="closed",
                description_text="Java and AWS in a closed role.",
                description_source="careers_page",
                must_have_skills=["Java", "AWS"],
                nice_to_have_skills=[],
            ),
        ]
    )
    db.commit()
    llm = RecordingLLM(text="Consider A1001 and the invented Z9999 role.")
    embedder = RecordingEmbedder()
    client, _app = _client(llm, embedder)
    try:
        chantilly = client.post("/public/chat", json={"message": "Jobs in Chantilly", "prior_codes": []})
        assert chantilly.status_code == 200
        body = chantilly.json()
        assert body["jobs"]
        assert {job["location"] for job in body["jobs"]} == {"Chantilly, VA"}

        follow = client.post(
            "/public/chat",
            json={"message": "Are these positions require SME experience", "prior_codes": ["A1001"]},
        )
        assert follow.status_code == 200
        assert [job["requisition_code"] for job in follow.json()["jobs"]] == ["A1001"]
        assert follow.json()["notice"] is None
        assert any("SME" in prompt["user"] and "A1001" in prompt["user"] for prompt in llm.prompts)

        still_there = client.post(
            "/public/chat",
            json={"message": "Do these require Java", "prior_codes": ["A1001"]},
        )
        assert [job["requisition_code"] for job in still_there.json()["jobs"]] == ["A1001"]

        everything = client.post("/public/chat", json={"message": "show me all positions", "prior_codes": []})
        assert everything.status_code == 200
        listed = {job["requisition_code"] for job in everything.json()["jobs"]}
        assert listed == {"A1001", "A1003", "N3001"}

        phrase = client.post(
            "/public/chat",
            json={"message": "Would like to see all AWS jobs in McLean", "prior_codes": []},
        )
        phrase_codes = {job["requisition_code"] for job in phrase.json()["jobs"]}
        assert "N3001" in phrase_codes
        assert "A1003" not in phrase_codes
        assert "G2002" not in phrase_codes

        outside = client.post(
            "/public/chat",
            json={"message": "Find me all jobs thar are NOT in Mclean", "prior_codes": []},
        )
        outside_jobs = outside.json()["jobs"]
        outside_codes = {job["requisition_code"] for job in outside_jobs}
        outside_cities = {job["location"] for job in outside_jobs}
        assert "N3001" not in outside_codes
        assert "G2002" not in outside_codes
        assert "A1001" in outside_codes
        assert "A1003" in outside_codes
        assert "McLean, VA" not in outside_cities
        assert {"Chantilly, VA", "Herndon, VA"} <= outside_cities

        aws = client.post("/public/chat", json={"message": "get me all AWS jobs", "prior_codes": []})
        aws_codes = aws.json()["prior_codes"]
        assert "N3001" in aws_codes
        assert "A1003" in aws_codes
        nearby = client.post(
            "/public/chat",
            json={"message": "what jobs are closest to Bethesda Maryland within 10", "prior_codes": aws_codes},
        )
        assert [job["requisition_code"] for job in nearby.json()["jobs"]] == ["N3001"]
        assert nearby.json()["jobs"][0]["distance_miles"] < 10
        wider = client.post(
            "/public/chat",
            json={"message": "what jobs are closest to Bethesda Maryland within 20", "prior_codes": aws_codes},
        )
        wider_codes = [job["requisition_code"] for job in wider.json()["jobs"]]
        assert wider_codes[0] == "N3001"
        assert "A1003" in wider_codes

        skills = client.post("/public/chat", json={"message": "Java and AWS", "prior_codes": []})
        codes = {job["requisition_code"] for job in skills.json()["jobs"]}
        assert "A1003" in codes
        assert "N3001" in codes
        assert "G2002" not in codes
        assert "A1001" not in codes
        missing = next(job for job in skills.json()["jobs"] if job["requisition_code"] == "N3001")
        assert missing["description_note"] == "Full description not on file."
        assert missing["confidence"] == "low"

        refusal = client.post(
            "/public/chat",
            json={"message": "list the candidates who know Java", "prior_codes": []},
        )
        assert refusal.json()["refusal"] is True
        assert refusal.json()["answer"] == REFUSAL_TEXT
        assert "Casey Nguyen" not in refusal.text
        assert llm.prompts == [] or all("Casey Nguyen" not in prompt["user"] for prompt in llm.prompts)

        down = RecordingLLM(fail=True)
        client.app.state.llm = down
        degraded = client.post("/public/chat", json={"message": "Jobs in Chantilly", "prior_codes": []})
        payload = degraded.json()
        assert payload["jobs"]
        assert payload["notice"] == "Explanations are unavailable right now."

        client.app.state.llm = RecordingLLM(text="Look at A1001 and also Z9999.")
        invented = client.post("/public/chat", json={"message": "Tell me about A1001", "prior_codes": []})
        assert "Z9999" not in invented.json()["answer"]
        assert [job["requisition_code"] for job in invented.json()["jobs"]] == ["A1001"]
    finally:
        client.__exit__(None, None, None)


def test_top_secret_resume_is_accepted_and_ssn_is_redacted(db):
    llm = RecordingLLM()
    embedder = RecordingEmbedder()
    client, _app = _client(llm, embedder)
    try:
        _login(client)
        accepted = client.post(
            "/admin/resumes",
            files={"file": ("resume.txt", RESUME.encode(), "text/plain")},
        )
        assert accepted.status_code == 200, accepted.text
        profile = accepted.json()["candidate"]
        assert profile["clearance"] == "ts_sci"
        assert profile["polygraph"] == "full_scope"
        assert profile["full_name"] == "Alex Rivera"
        assert profile["location"] == "Chantilly, VA"
        assert {skill["name"] for skill in profile["skills"]} >= {"Java", "Python", "AWS"}
        assert profile["summary"]
        assert accepted.json()["already_ingested"] is False
        again = client.post(
            "/admin/resumes",
            files={"file": ("resume.txt", RESUME.encode(), "text/plain")},
        )
        assert again.status_code == 200, again.text
        assert again.json()["already_ingested"] is True
        assert again.json()["candidate_id"] == profile["id"]
        opened = client.get(f"/admin/resumes/{profile['id']}")
        assert opened.status_code == 200
        assert opened.json()["candidate"]["full_name"] == "Alex Rivera"
        listed = client.get("/admin/resumes")
        assert listed.status_code == 200
        assert profile["id"] in {row["id"] for row in listed.json()["candidates"]}

        rejected = client.post(
            "/admin/resumes",
            files={"file": ("resume.doc", b"not a modern file", "application/msword")},
        )
        assert rejected.status_code == 400
        assert "Save as DOCX or PDF" in rejected.json()["detail"]

        uploaded = client.post(
            "/admin/resumes",
            files={"file": ("ssn.txt", SSN_RESUME.encode(), "text/plain")},
        )
        assert uploaded.status_code == 200, uploaded.text
        candidate_id = uploaded.json()["candidate"]["id"]
        from app.models import Candidate

        stored = db.get(Candidate, candidate_id)
        db.refresh(stored)
        assert "123-45-6789" not in (stored.redacted_text or "")
        assert "987654321" not in (stored.redacted_text or "")
        assert all("123-45-6789" not in prompt["user"] and "987654321" not in prompt["user"] for prompt in llm.prompts)
        confirmed = client.post(
            f"/admin/resumes/{candidate_id}/confirm",
            json={
                "full_name": "Alex Rivera",
                "location": "Chantilly, VA",
                "skills": [
                    {"name": "Java", "years": 6},
                    {"name": "Python", "years": 6},
                    {"name": "AWS", "years": 4},
                ],
                "titles": ["Software Engineer"],
                "clearance": "ts_sci",
                "polygraph": "full_scope",
                "summary": "Engineer in Chantilly using Java, Python, and AWS.",
            },
        )
        assert confirmed.status_code == 200, confirmed.text
        assert all("123-45-6789" not in text and "987654321" not in text for text in embedder.documents)
    finally:
        client.__exit__(None, None, None)


def test_resume_ranks_matching_job_and_shows_both_scores(db):
    db.add_all(
        [
            Job(
                requisition_code="A1003",
                title="Software Developer",
                location="Chantilly, VA",
                status="open",
                description_text="Java, Python, and AWS services.",
                description_source="careers_page",
                must_have_skills=["Java", "Python"],
                nice_to_have_skills=["AWS"],
                summary="Java Python AWS",
            ),
            Job(
                requisition_code="A1006",
                title="Network Engineer",
                location="Herndon, VA",
                status="open",
                description_text="Routing and switching for a campus network.",
                description_source="careers_page",
                must_have_skills=["Routing"],
                nice_to_have_skills=[],
                summary="Network routing",
            ),
        ]
    )
    db.commit()
    llm = RecordingLLM(text="The software role overlaps Java, Python, and AWS.")
    embedder = RecordingEmbedder()
    client, _app = _client(llm, embedder)
    try:
        _login(client)
        uploaded = client.post(
            "/admin/resumes",
            files={"file": ("alex.txt", RESUME.encode(), "text/plain")},
        )
        candidate_id = uploaded.json()["candidate"]["id"]
        ranked = client.post(
            f"/admin/resumes/{candidate_id}/confirm",
            json={
                "full_name": "Alex Rivera",
                "location": "Chantilly, VA",
                "skills": [
                    {"name": "Java", "years": 6},
                    {"name": "Python", "years": 5},
                    {"name": "AWS", "years": 4},
                ],
                "titles": ["Software Engineer"],
                "clearance": "ts_sci",
                "polygraph": "full_scope",
                "summary": "Chantilly engineer with Java, Python, and AWS.",
            },
        )
        assert ranked.status_code == 200, ranked.text
        matches = ranked.json()["matches"]
        assert matches[0]["requisition_code"] == "A1003"
        assert matches[0]["final"] > matches[1]["final"]
        assert matches[0]["skill_score"] is not None
        assert matches[0]["semantic"] is not None
        assert "skill_score" in matches[0] and "semantic" in matches[0]
    finally:
        client.__exit__(None, None, None)


def test_long_resume_stores_one_vector_and_overlapping_chunks(db):
    from app.core.tokens import CHUNK_OVERLAP, CHUNK_TOKENS, count_tokens, encode_ids, token_windows
    from app.models import Candidate, CandidateChunk

    sentence = "Designed Java services on AWS using Python and PostgreSQL for a federal program in Chantilly. "
    text = "Alex Rivera, software engineer. "
    while count_tokens(text) < 3000:
        text += sentence
    llm = RecordingLLM()
    embedder = RecordingEmbedder()
    client, _app = _client(llm, embedder)
    try:
        _login(client)
        uploaded = client.post("/admin/resumes", files={"file": ("long.txt", text.encode(), "text/plain")})
        assert uploaded.status_code == 200, uploaded.text
        candidate_id = uploaded.json()["candidate"]["id"]
        confirmed = client.post(
            f"/admin/resumes/{candidate_id}/confirm",
            json={
                "full_name": "Alex Rivera",
                "skills": [{"name": "Java", "years": 3}],
                "titles": ["Engineer"],
                "summary": text,
                "clearance": None,
                "polygraph": None,
            },
        )
        assert confirmed.status_code == 200, confirmed.text
        stored = db.get(Candidate, candidate_id)
        db.refresh(stored)
        assert stored.embedding is not None
        assert len(list(stored.embedding)) == 768
        windows = token_windows(stored.redacted_text or "")
        chunks = db.query(CandidateChunk).filter(CandidateChunk.candidate_id == stored.id).order_by(CandidateChunk.ord).all()
        assert len(chunks) == len(windows)
        assert all(len(encode_ids(chunk.text)) > 0 for chunk in chunks)
        assert all(len(window) == CHUNK_TOKENS for window in windows[:-1])
        for previous, nxt in zip(windows, windows[1:]):
            assert previous[-CHUNK_OVERLAP:] == nxt[:CHUNK_OVERLAP]
        assert count_tokens(embedder.documents[0]) <= 1024
    finally:
        client.__exit__(None, None, None)


def test_lockout_is_per_ip(db):
    app = create_app()
    blocked = TestClient(app, client=("10.1.1.1", 5000))
    other = TestClient(app, client=("10.2.2.2", 5000))
    with blocked, other:
        app.state.llm = RecordingLLM()
        app.state.embedder = RecordingEmbedder()
        for _ in range(8):
            response = blocked.post("/admin/login", json={"password": "nope"})
            assert response.status_code == 401
        locked = blocked.post("/admin/login", json={"password": "correct-horse"})
        assert locked.status_code == 429
        allowed = other.post("/admin/login", json={"password": "correct-horse"})
        assert allowed.status_code == 200
