"""Re-embed every job and confirmed candidate after an embedding model change."""

from sqlalchemy import select

from app.config import get_settings
from app.core.embed import FastEmbedder
from app.core.tokens import job_vector_text, chunk_text, candidate_vector_text
from app.db import admin_session
from app.models import Candidate, CandidateChunk, Job, JobChunk


def main() -> None:
    settings = get_settings()
    embedder = FastEmbedder(settings.embedding_model)
    session = admin_session()
    try:
        for job in session.scalars(select(Job)).all():
            session.query(JobChunk).filter(JobChunk.job_id == job.id).delete()
            text = job_vector_text(job.title or "", job.location or "", job.summary or "", job.description_text or "")
            if (job.description_text or "").strip() or (job.title or "").strip():
                job.embedding = embedder.embed_documents([text])[0]
            chunks = chunk_text(job.description_text or "")
            vectors = embedder.embed_documents(chunks) if chunks else []
            for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
                session.add(JobChunk(job_id=job.id, ord=index, text=chunk, embedding=vector))
        for candidate in session.scalars(select(Candidate).where(Candidate.status == "confirmed")).all():
            names = [row["name"] if isinstance(row, dict) else str(row) for row in (candidate.skills or [])]
            text = candidate_vector_text(candidate.summary or "", list(candidate.titles or []), names)
            candidate.embedding = embedder.embed_documents([text])[0]
            session.query(CandidateChunk).filter(CandidateChunk.candidate_id == candidate.id).delete()
            chunks = chunk_text(candidate.redacted_text or "")
            vectors = embedder.embed_documents(chunks) if chunks else []
            for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
                session.add(CandidateChunk(candidate_id=candidate.id, ord=index, text=chunk, embedding=vector))
        session.commit()
    finally:
        session.close()


if __name__ == "__main__":
    main()
