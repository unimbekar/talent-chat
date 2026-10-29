"""Proposed or funded, from a proposal word in parentheses on the careers listing."""

from alembic import op

revision = "0014_job_funding"
down_revision = "0013_site_visitors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS funding TEXT NOT NULL DEFAULT 'funded'")


def downgrade() -> None:
    op.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS funding")
