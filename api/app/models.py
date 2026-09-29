"""Phase 1 tables. outreach and ingest_events arrive in later phases."""

from datetime import datetime
import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Computed, DateTime, Float, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, validates

from app.core.us_states import state_from_location


class Base(DeclarativeBase):
    pass


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    requisition_code: Mapped[str] = mapped_column(Text, unique=True, index=True)
    site_job_id: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text, index=True)
    program_tag: Mapped[str | None] = mapped_column(Text)
    external_req: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="open", index=True)
    source_line: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    description_text: Mapped[str | None] = mapped_column(Text)
    description_source: Mapped[str] = mapped_column(Text, default="none")
    description_hash: Mapped[str | None] = mapped_column(Text)
    careers_description_text: Mapped[str | None] = mapped_column(Text)
    careers_description_hash: Mapped[str | None] = mapped_column(Text)
    must_have_skills: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")
    nice_to_have_skills: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")
    skill_quotes: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    clearance_required: Mapped[str | None] = mapped_column(Text)
    polygraph_required: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768))
    tsv: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description_text, ''))",
            persisted=True,
        ),
    )
    detail_error: Mapped[str | None] = mapped_column(Text)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    chunks: Mapped[list["JobChunk"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class JobChunk(Base):
    __tablename__ = "job_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    ord: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768))
    job: Mapped[Job] = relationship(back_populates="chunks")


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    file_sha256: Mapped[str] = mapped_column(Text, unique=True)
    original_filename: Mapped[str | None] = mapped_column(Text)
    original_path: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="pending_review")
    full_name: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    # Two-letter home state derived from location. Set by _derive_state; do not assign directly.
    state: Mapped[str | None] = mapped_column(Text, index=True)
    skills: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    titles: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")
    clearance: Mapped[str | None] = mapped_column(Text)
    polygraph: Mapped[str | None] = mapped_column(Text)
    citizenship: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    redacted_text: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768))
    tsv: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', coalesce(redacted_text, ''))", persisted=True),
    )
    outreach_opt_in: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    google_file_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    chunks: Mapped[list["CandidateChunk"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )

    @validates("location")
    def _derive_state(self, _key: str, value: str | None) -> str | None:
        self.state = state_from_location(value)
        return value


class CandidateChunk(Base):
    __tablename__ = "candidate_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    ord: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768))
    candidate: Mapped[Candidate] = relationship(back_populates="chunks")


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    skill_score: Mapped[float | None] = mapped_column(Float)
    raw_cosine: Mapped[float | None] = mapped_column(Float)
    semantic: Mapped[float | None] = mapped_column(Float)
    final: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[str | None] = mapped_column(Text)
    overlap_skills: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")
    clearance_flag: Mapped[str | None] = mapped_column(Text)
    job_quotes: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    resume_quotes: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    explanation: Mapped[str | None] = mapped_column(Text)


class SkillSynonym(Base):
    __tablename__ = "skill_synonyms"

    alias: Mapped[str] = mapped_column(Text, primary_key=True)
    canonical: Mapped[str] = mapped_column(Text, primary_key=True)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    actor: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    outcome: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    ip: Mapped[str] = mapped_column(Text, index=True)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CrawlState(Base):
    __tablename__ = "crawl_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_ok: Mapped[bool | None] = mapped_column(Boolean)
    last_error: Mapped[str | None] = mapped_column(Text)
    last_rows: Mapped[int | None] = mapped_column(Integer)
