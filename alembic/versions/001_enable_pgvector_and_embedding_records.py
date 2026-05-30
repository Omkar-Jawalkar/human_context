"""enable pgvector and embedding_records table

Revision ID: 001
Revises:
Create Date: 2026-05-30

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

from app.core.config import settings

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "embedding_records",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("namespace", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("metadata", sa.dialects.postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("embedding", Vector(settings.embedding_dimensions), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_embedding_records_namespace",
        "embedding_records",
        ["namespace"],
    )
    op.execute(
        """
        CREATE INDEX ix_embedding_records_embedding_hnsw
        ON embedding_records
        USING hnsw (embedding vector_cosine_ops)
        """
    )


def downgrade() -> None:
    op.drop_index("ix_embedding_records_embedding_hnsw", table_name="embedding_records")
    op.drop_index("ix_embedding_records_namespace", table_name="embedding_records")
    op.drop_table("embedding_records")
    op.execute("DROP EXTENSION IF EXISTS vector")
