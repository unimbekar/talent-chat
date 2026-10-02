"""A note kept with a job the recruiter closed."""

from alembic import op

revision = "0003_job_close_note"
down_revision = "0002_candidate_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS close_note TEXT")
    op.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS closed_manually BOOLEAN NOT NULL DEFAULT false")


def downgrade() -> None:
    op.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS closed_manually")
    op.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS close_note")
