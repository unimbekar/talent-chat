"""Handbook and policy documents. The public role cannot read them."""

from alembic import op

revision = "0008_knowledge"
down_revision = "0007_admin_password"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE knowledge_documents (
          id UUID PRIMARY KEY,
          title TEXT NOT NULL,
          audience TEXT NOT NULL,
          source_name TEXT NOT NULL DEFAULT '',
          body TEXT NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_knowledge_documents_audience ON knowledge_documents (audience)")
    op.execute(
        """
        CREATE TABLE knowledge_chunks (
          id UUID PRIMARY KEY,
          document_id UUID NOT NULL REFERENCES knowledge_documents (id) ON DELETE CASCADE,
          ord INTEGER NOT NULL,
          text TEXT NOT NULL,
          embedding vector(768)
        )
        """
    )
    op.execute("CREATE INDEX ix_knowledge_chunks_document_id ON knowledge_chunks (document_id)")
    op.execute("GRANT ALL ON knowledge_documents, knowledge_chunks TO app_admin")
    op.execute("REVOKE ALL ON knowledge_documents, knowledge_chunks FROM app_public")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS knowledge_chunks")
    op.execute("DROP TABLE IF EXISTS knowledge_documents")
