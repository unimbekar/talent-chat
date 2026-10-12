"""Knowledge sections: each chunk keeps the heading it sits under."""

from alembic import op

revision = "0009_knowledge_sections"
down_revision = "0008_knowledge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE knowledge_chunks ADD COLUMN heading TEXT")
    op.execute("ALTER TABLE knowledge_chunks ADD COLUMN kicker TEXT")
    # Documents split before sections existed are split again when the API starts.
    op.execute("ALTER TABLE knowledge_documents ADD COLUMN chunk_version INTEGER NOT NULL DEFAULT 1")


def downgrade() -> None:
    op.execute("ALTER TABLE knowledge_documents DROP COLUMN IF EXISTS chunk_version")
    op.execute("ALTER TABLE knowledge_chunks DROP COLUMN IF EXISTS kicker")
    op.execute("ALTER TABLE knowledge_chunks DROP COLUMN IF EXISTS heading")
