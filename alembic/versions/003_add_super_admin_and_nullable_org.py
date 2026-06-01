"""add super_admin and nullable organization_id on users

Revision ID: 003
Revises: 002
Create Date: 2026-06-01

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SUPER_ADMIN_ORG_CHECK = (
    "(super_admin = true AND organization_id IS NULL) OR (super_admin = false)"
)


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "super_admin",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.alter_column("users", "organization_id", nullable=True)
    op.create_check_constraint(
        "ck_users_super_admin_organization",
        "users",
        _SUPER_ADMIN_ORG_CHECK,
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_super_admin_organization", "users", type_="check")
    op.execute(
        sa.text(
            "UPDATE users SET organization_id = (SELECT id FROM organizations LIMIT 1) "
            "WHERE organization_id IS NULL"
        )
    )
    op.alter_column("users", "organization_id", nullable=False)
    op.drop_column("users", "super_admin")
