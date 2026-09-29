"""Home state on candidates, so Find candidates can filter by where a person lives."""

from alembic import op
import sqlalchemy as sa

from app.core.us_states import state_from_location

revision = "0002_candidate_state"
down_revision = "0001_phase1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS state TEXT")
    op.execute("CREATE INDEX IF NOT EXISTS ix_candidates_state ON candidates (state)")
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, location FROM candidates WHERE location IS NOT NULL")).all()
    for row_id, location in rows:
        code = state_from_location(location)
        if code:
            bind.execute(sa.text("UPDATE candidates SET state = :code WHERE id = :id"), {"code": code, "id": row_id})


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_candidates_state")
    op.execute("ALTER TABLE candidates DROP COLUMN IF EXISTS state")
