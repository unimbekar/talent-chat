"""Desk password hash, readable only by the admin role."""

from alembic import op

revision = "0007_admin_password"
down_revision = "0006_push"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE admin_password (
          id INTEGER PRIMARY KEY,
          password_hash TEXT NOT NULL,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("GRANT ALL ON admin_password TO app_admin")
    op.execute("REVOKE ALL ON admin_password FROM app_public")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS admin_password")
