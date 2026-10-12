"""Careers-site visits: one row per page, posting, or apply view, keyed by an anonymous visitor id."""

from alembic import op

revision = "0012_site_visits"
down_revision = "0011_desk_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE site_visits (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            at TIMESTAMPTZ NOT NULL DEFAULT now(),
            visitor UUID NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('page', 'posting', 'apply')),
            path TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'direct',
            device TEXT NOT NULL DEFAULT 'desktop' CHECK (device IN ('desktop', 'mobile', 'tablet'))
        )
        """
    )
    op.execute("CREATE INDEX ix_site_visits_at ON site_visits (at)")
    op.execute("CREATE INDEX ix_site_visits_visitor_at ON site_visits (visitor, at)")
    # The server records visits with the admin role; the public role never reads or writes them.
    op.execute("GRANT ALL ON site_visits TO app_admin")
    op.execute("REVOKE ALL ON site_visits FROM app_public")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS site_visits")
