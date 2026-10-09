"""Careers-site applications linked to a submission."""

from alembic import op

revision = "0005_applications"
down_revision = "0004_submissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE job_applications (
          id UUID PRIMARY KEY,
          submission_id UUID NOT NULL UNIQUE REFERENCES submissions(id) ON DELETE CASCADE,
          candidate_id UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
          job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
          full_name TEXT NOT NULL,
          email TEXT NOT NULL,
          phone TEXT NOT NULL,
          location TEXT NOT NULL,
          salary_usd INTEGER NOT NULL,
          start_on DATE NOT NULL,
          years_experience INTEGER NOT NULL,
          fsp BOOLEAN NOT NULL,
          last_fsp_on DATE,
          last_tssci_on DATE,
          note TEXT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_job_applications_job ON job_applications (job_id)")
    op.execute("GRANT ALL PRIVILEGES ON job_applications TO app_admin")
    op.execute("REVOKE ALL ON job_applications FROM app_public")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS job_applications")
