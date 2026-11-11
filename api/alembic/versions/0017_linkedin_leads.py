"""People a recruiter saved from their own LinkedIn search."""

from alembic import op

revision = "0017_linkedin_leads"
down_revision = "0016_resume_updates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS linkedin_leads (
          id UUID PRIMARY KEY,
          job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
          full_name TEXT NOT NULL,
          profile_url TEXT NOT NULL,
          headline TEXT NOT NULL DEFAULT '',
          note TEXT NOT NULL DEFAULT '',
          created_by TEXT NOT NULL DEFAULT '',
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (job_id, profile_url)
        )
        """
    )
    op.execute("GRANT ALL ON linkedin_leads TO app_admin")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS linkedin_leads")
