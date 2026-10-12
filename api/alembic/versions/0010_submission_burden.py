"""Submission burden: the calculator inputs saved with a submission."""

from alembic import op

revision = "0010_submission_burden"
down_revision = "0009_knowledge_sections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE submissions ADD COLUMN burden JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE submissions DROP COLUMN IF EXISTS burden")
