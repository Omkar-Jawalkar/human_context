"""add context_user_id and use_thread_history; drop use_context

Revision ID: 006
Revises: 005
Create Date: 2026-06-05

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chat_threads",
        sa.Column("context_user_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "chat_threads",
        sa.Column(
            "use_thread_history",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )
    op.execute("UPDATE chat_threads SET context_user_id = user_id")
    op.alter_column("chat_threads", "context_user_id", nullable=False)
    op.create_foreign_key(
        "fk_chat_threads_context_user_id_users",
        "chat_threads",
        "users",
        ["context_user_id"],
        ["id"],
    )
    op.create_index(
        "ix_chat_threads_context_user_id",
        "chat_threads",
        ["context_user_id"],
    )
    op.drop_column("chat_threads", "use_context")


def downgrade() -> None:
    op.add_column(
        "chat_threads",
        sa.Column(
            "use_context",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )
    op.drop_index("ix_chat_threads_context_user_id", table_name="chat_threads")
    op.drop_constraint(
        "fk_chat_threads_context_user_id_users",
        "chat_threads",
        type_="foreignkey",
    )
    op.drop_column("chat_threads", "use_thread_history")
    op.drop_column("chat_threads", "context_user_id")
