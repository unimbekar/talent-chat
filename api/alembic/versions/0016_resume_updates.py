"""Justifications recruiters attach when a résumé misses a requirement."""

from alembic import op

revision = "0016_resume_updates"
down_revision = "0015_removed_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS resume_updates (
          id UUID PRIMARY KEY,
          candidate_id UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
          job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
          items JSONB NOT NULL DEFAULT '[]',
          updated_by TEXT NOT NULL DEFAULT '',
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (candidate_id, job_id)
        )
        """
    )
    op.execute("GRANT ALL ON resume_updates TO app_admin")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS resume_updates")
