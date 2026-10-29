"""Remember jobs an admin deleted so the careers crawl does not create them again."""

from alembic import op

revision = "0015_removed_jobs"
down_revision = "0014_job_funding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS removed_jobs (
          requisition_code TEXT PRIMARY KEY,
          removed_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("GRANT ALL ON removed_jobs TO app_admin")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS removed_jobs")
