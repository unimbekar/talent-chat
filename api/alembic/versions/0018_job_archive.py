"""Closed jobs can be archived so they leave the closed list."""

from alembic import op

revision = "0018_job_archive"
down_revision = "0017_linkedin_leads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS archived_at")
