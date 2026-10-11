"""Phone push notifications: the server's VAPID key and each subscribed device."""

from alembic import op

revision = "0006_push"
down_revision = "0005_applications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Not in settings: app_public can read that table.
    op.execute(
        """
        CREATE TABLE push_keys (
          id INTEGER PRIMARY KEY,
          private_pem TEXT NOT NULL,
          public_key TEXT NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE push_subscriptions (
          id UUID PRIMARY KEY,
          endpoint TEXT NOT NULL UNIQUE,
          p256dh TEXT NOT NULL,
          auth TEXT NOT NULL,
          device TEXT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          last_sent_at TIMESTAMPTZ
        )
        """
    )
    for table in ("push_keys", "push_subscriptions"):
        op.execute(f"GRANT ALL PRIVILEGES ON {table} TO app_admin")
        op.execute(f"REVOKE ALL ON {table} FROM app_public")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS push_subscriptions")
    op.execute("DROP TABLE IF EXISTS push_keys")
