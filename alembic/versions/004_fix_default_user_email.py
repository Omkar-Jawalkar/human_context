"""fix default import user email for pydantic EmailStr validation

Revision ID: 004
Revises: 003
Create Date: 2026-06-05

"""

from typing import Sequence, Union

from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_EMAIL = "default@localhost"
_NEW_EMAIL = "default@example.com"


def upgrade() -> None:
    op.execute(
        f"UPDATE users SET email = '{_NEW_EMAIL}' WHERE email = '{_OLD_EMAIL}'"
    )


def downgrade() -> None:
    op.execute(
        f"UPDATE users SET email = '{_OLD_EMAIL}' WHERE email = '{_NEW_EMAIL}'"
    )
