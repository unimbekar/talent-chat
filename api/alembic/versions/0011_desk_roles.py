"""Desk roles: named recruiter accounts, and the role each session signed in with."""

from alembic import op

revision = "0011_desk_roles"
down_revision = "0010_submission_burden"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE desk_users (
            id UUID PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            display_name TEXT,
            role TEXT NOT NULL DEFAULT 'recruiter' CHECK (role IN ('admin', 'recruiter')),
            password_hash TEXT NOT NULL,
            active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_login_at TIMESTAMPTZ
        )
        """
    )
    op.execute("CREATE INDEX ix_desk_users_email ON desk_users (email)")
    # Password hashes stay away from the public role, like admin_password.
    op.execute("GRANT ALL ON desk_users TO app_admin")
    op.execute("REVOKE ALL ON desk_users FROM app_public")
    op.execute("ALTER TABLE admin_sessions ADD COLUMN role TEXT NOT NULL DEFAULT 'admin'")
    op.execute("ALTER TABLE admin_sessions ADD COLUMN email TEXT")
    op.execute("ALTER TABLE admin_sessions ADD COLUMN user_id UUID REFERENCES desk_users(id) ON DELETE CASCADE")
    op.execute("CREATE INDEX ix_admin_sessions_user_id ON admin_sessions (user_id)")


def downgrade() -> None:
    op.execute("ALTER TABLE admin_sessions DROP COLUMN IF EXISTS user_id")
    op.execute("ALTER TABLE admin_sessions DROP COLUMN IF EXISTS email")
    op.execute("ALTER TABLE admin_sessions DROP COLUMN IF EXISTS role")
    op.execute("DROP TABLE IF EXISTS desk_users")
