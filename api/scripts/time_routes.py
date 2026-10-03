"""Time the non-model admin and public routes against the configured database.

    docker compose exec -T api /app/.venv/bin/python - < api/scripts/time_routes.py
"""

import time

from sqlalchemy import select

from app.admin import routes as admin
from app.config import get_settings
from app.core.embed import FastEmbedder
from app.db import admin_session, public_session
from app.models import Candidate, Job
from app.public.search import search_jobs


def timed(label: str, call, repeat: int = 3) -> None:
    runs = []
    for _ in range(repeat):
        started = time.perf_counter()
        call()
        runs.append(time.perf_counter() - started)
    print(f"{label:<34} first {runs[0] * 1000:7.0f} ms   best {min(runs) * 1000:7.0f} ms")


def main() -> None:
    session = admin_session()
    job = session.scalars(select(Job).where(Job.status == "open")).first()
    person = session.scalars(select(Candidate)).first()
    embedder = FastEmbedder(get_settings().embedding_model)
    embedder.embed_query("warm up")

    timed("GET /admin/jobs", lambda: admin.list_jobs(session))
    timed("GET /admin/jobs/{code}", lambda: admin.get_job(job.requisition_code, session))
    timed("GET /admin/jobs/{code}/candidates", lambda: admin.job_candidates(job.requisition_code, session))
    timed("GET /admin/review", lambda: admin.review_pair(job.requisition_code, person.id, session))
    timed("GET /admin/resumes", lambda: admin.list_resumes(session, q="", category="", page=1, page_size=25))
    timed("GET /admin/resumes?q=java", lambda: admin.list_resumes(session, q="java", category="", page=1, page_size=25))
    timed("GET /admin/resumes/{id}", lambda: admin.get_resume(person.id, session))
    timed("GET /admin/candidates/emails", lambda: admin.all_candidate_emails(session))

    public = public_session()
    timed("public search_jobs (no model)", lambda: search_jobs(public, "java developer in Chantilly", [], embedder=embedder))


if __name__ == "__main__":
    main()
