"""Phase 1 schema: vector extension, both roles, tables, and HNSW cosine indexes."""

from alembic import op

from app.core.skills import SEED_SYNONYMS

revision = "0001_phase1"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            """
            DO $$ BEGIN
              CREATE ROLE app_admin LOGIN;
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
            """
        )
        op.execute(
            """
            DO $$ BEGIN
              CREATE ROLE app_public LOGIN;
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
            """
        )
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("GRANT USAGE ON SCHEMA public TO app_admin, app_public")
    op.execute(
        """
        CREATE TABLE jobs (
          id UUID PRIMARY KEY,
          requisition_code TEXT NOT NULL UNIQUE,
          site_job_id TEXT,
          title TEXT,
          location TEXT,
          program_tag TEXT,
          external_req TEXT,
          status TEXT NOT NULL DEFAULT 'open',
          source_line TEXT,
          source_url TEXT,
          needs_review BOOLEAN NOT NULL DEFAULT FALSE,
          description_text TEXT,
          description_source TEXT NOT NULL DEFAULT 'none',
          description_hash TEXT,
          careers_description_text TEXT,
          careers_description_hash TEXT,
          must_have_skills TEXT[] NOT NULL DEFAULT '{}',
          nice_to_have_skills TEXT[] NOT NULL DEFAULT '{}',
          skill_quotes JSONB NOT NULL DEFAULT '{}',
          clearance_required TEXT,
          polygraph_required TEXT,
          summary TEXT,
          embedding vector(768),
          tsv tsvector GENERATED ALWAYS AS (
            to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description_text, ''))
          ) STORED,
          detail_error TEXT,
          last_seen_at TIMESTAMPTZ,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE job_chunks (
          id UUID PRIMARY KEY,
          job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
          ord INTEGER NOT NULL,
          text TEXT NOT NULL,
          embedding vector(768)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE candidates (
          id UUID PRIMARY KEY,
          file_sha256 TEXT NOT NULL UNIQUE,
          original_filename TEXT,
          original_path TEXT,
          status TEXT NOT NULL DEFAULT 'pending_review',
          full_name TEXT,
          email TEXT,
          phone TEXT,
          location TEXT,
          skills JSONB NOT NULL DEFAULT '[]',
          titles TEXT[] NOT NULL DEFAULT '{}',
          clearance TEXT,
          polygraph TEXT,
          citizenship TEXT,
          summary TEXT,
          redacted_text TEXT,
          embedding vector(768),
          tsv tsvector GENERATED ALWAYS AS (
            to_tsvector('english', coalesce(redacted_text, ''))
          ) STORED,
          outreach_opt_in BOOLEAN NOT NULL DEFAULT FALSE,
          google_file_id TEXT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE candidate_chunks (
          id UUID PRIMARY KEY,
          candidate_id UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
          ord INTEGER NOT NULL,
          text TEXT NOT NULL,
          embedding vector(768)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE matches (
          id UUID PRIMARY KEY,
          candidate_id UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
          job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
          skill_score DOUBLE PRECISION,
          raw_cosine DOUBLE PRECISION,
          semantic DOUBLE PRECISION,
          final DOUBLE PRECISION,
          confidence TEXT,
          overlap_skills TEXT[] NOT NULL DEFAULT '{}',
          clearance_flag TEXT,
          job_quotes JSONB NOT NULL DEFAULT '[]',
          resume_quotes JSONB NOT NULL DEFAULT '[]',
          explanation TEXT
        )
        """
    )
    op.execute(
        """
        CREATE TABLE skill_synonyms (
          alias TEXT NOT NULL,
          canonical TEXT NOT NULL,
          PRIMARY KEY (alias, canonical)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE settings (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL DEFAULT '',
          is_public BOOLEAN NOT NULL DEFAULT TRUE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE audit_log (
          id UUID PRIMARY KEY,
          actor TEXT NOT NULL,
          action TEXT NOT NULL,
          subject_id UUID,
          outcome TEXT,
          at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE admin_sessions (
          id UUID PRIMARY KEY,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          expires_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE login_attempts (
          id UUID PRIMARY KEY,
          ip TEXT NOT NULL,
          failed_count INTEGER NOT NULL DEFAULT 0,
          locked_until TIMESTAMPTZ
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX ix_login_attempts_ip ON login_attempts (ip)")
    op.execute(
        """
        CREATE TABLE crawl_state (
          id INTEGER PRIMARY KEY,
          last_started_at TIMESTAMPTZ,
          last_finished_at TIMESTAMPTZ,
          last_ok BOOLEAN,
          last_error TEXT,
          last_rows INTEGER
        )
        """
    )
    op.execute("CREATE INDEX ix_jobs_status ON jobs (status)")
    op.execute("CREATE INDEX ix_jobs_location ON jobs (location)")
    op.execute("CREATE INDEX ix_jobs_must_have ON jobs USING gin (must_have_skills)")
    op.execute("CREATE INDEX ix_jobs_nice_have ON jobs USING gin (nice_to_have_skills)")
    op.execute("CREATE INDEX ix_jobs_tsv ON jobs USING gin (tsv)")
    op.execute("CREATE INDEX ix_candidates_outreach ON candidates (outreach_opt_in)")
    op.execute("CREATE INDEX ix_jobs_embedding ON jobs USING hnsw (embedding vector_cosine_ops)")
    op.execute("CREATE INDEX ix_job_chunks_embedding ON job_chunks USING hnsw (embedding vector_cosine_ops)")
    op.execute("CREATE INDEX ix_candidates_embedding ON candidates USING hnsw (embedding vector_cosine_ops)")
    op.execute(
        "CREATE INDEX ix_candidate_chunks_embedding ON candidate_chunks USING hnsw (embedding vector_cosine_ops)"
    )
    bind = op.get_bind()
    for alias, canonical in SEED_SYNONYMS:
        bind.exec_driver_sql(
            "INSERT INTO skill_synonyms (alias, canonical) VALUES (%(alias)s, %(canonical)s) ON CONFLICT DO NOTHING",
            {"alias": alias, "canonical": canonical},
        )
    op.execute(
        """
        INSERT INTO settings (key, value, is_public) VALUES
          ('company_name', 'Janus Soft Inc.', TRUE),
          ('careers_url', 'https://www.janus-soft.com/career', TRUE)
        ON CONFLICT DO NOTHING
        """
    )
    op.execute("INSERT INTO crawl_state (id) VALUES (1) ON CONFLICT DO NOTHING")
    op.execute("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO app_admin")
    op.execute("GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO app_admin")
    op.execute("GRANT SELECT ON jobs, job_chunks, skill_synonyms, settings TO app_public")
    op.execute("REVOKE ALL ON candidates, candidate_chunks, matches, audit_log, admin_sessions, login_attempts, crawl_state FROM app_public")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS crawl_state, login_attempts, admin_sessions, audit_log, settings, skill_synonyms, matches, candidate_chunks, candidates, job_chunks, jobs CASCADE")
