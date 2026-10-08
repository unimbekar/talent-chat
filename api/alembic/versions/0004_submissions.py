"""Submission pipeline: one row per candidate and job, plus history and comments."""

from alembic import op

revision = "0004_submissions"
down_revision = "0003_job_close_note"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE submissions (
          id UUID PRIMARY KEY,
          candidate_id UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
          job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
          stage TEXT NOT NULL DEFAULT 'submitted',
          salary_usd INTEGER,
          salary_note TEXT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE submission_events (
          id UUID PRIMARY KEY,
          submission_id UUID NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
          kind TEXT NOT NULL,
          from_stage TEXT,
          to_stage TEXT,
          body TEXT,
          salary_usd INTEGER,
          at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE submission_comments (
          id UUID PRIMARY KEY,
          submission_id UUID NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
          body TEXT NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE candidate_comments (
          id UUID PRIMARY KEY,
          candidate_id UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
          body TEXT NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX uq_submissions_candidate_job ON submissions (candidate_id, job_id)")
    op.execute("CREATE INDEX ix_submissions_job ON submissions (job_id)")
    op.execute("CREATE INDEX ix_submissions_stage ON submissions (stage)")
    op.execute("CREATE INDEX ix_submissions_updated ON submissions (updated_at DESC)")
    op.execute("CREATE INDEX ix_submission_events_submission ON submission_events (submission_id, at)")
    op.execute("CREATE INDEX ix_submission_comments_submission ON submission_comments (submission_id, created_at)")
    op.execute("CREATE INDEX ix_candidate_comments_candidate ON candidate_comments (candidate_id, created_at)")
    op.execute(
        "GRANT ALL PRIVILEGES ON submissions, submission_events, submission_comments, candidate_comments TO app_admin"
    )
    op.execute(
        "REVOKE ALL ON submissions, submission_events, submission_comments, candidate_comments FROM app_public"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS submission_comments, submission_events, candidate_comments, submissions CASCADE")
