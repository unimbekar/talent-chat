"""One row per careers-site browser: the IP it connected from and a city-level place."""

from alembic import op

revision = "0013_site_visitors"
down_revision = "0012_site_visits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE site_visitors (
            visitor UUID PRIMARY KEY,
            ip TEXT NOT NULL,
            city TEXT,
            region TEXT,
            country TEXT,
            first_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_site_visitors_last_at ON site_visitors (last_at)")
    op.execute("GRANT ALL ON site_visitors TO app_admin")
    op.execute("REVOKE ALL ON site_visitors FROM app_public")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS site_visitors")
