"""team roles (handoff v1.1): OWNER, DIRECTOR, PROJECT_MANAGER, CONTENT_SPECIALIST, DESIGNER, EDITOR

Data-only migration: the role column is plain text (non-native enum), so only
existing values are remapped. Old MANAGER -> PROJECT_MANAGER, old MEMBER ->
EDITOR (the OWNER can correct individual users later). The OWNER's empty
capability list gets the defaults used for the OWNER's "normal view" menu.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OWNER_DEFAULT_CAPABILITIES = '["PUBLISH", "SYSTEM_ADMIN"]'


def upgrade() -> None:
    op.execute(sa.text("UPDATE users SET role = 'PROJECT_MANAGER' WHERE role = 'MANAGER'"))
    op.execute(sa.text("UPDATE users SET role = 'EDITOR' WHERE role = 'MEMBER'"))
    op.execute(
        sa.text(
            "UPDATE users SET capabilities = :caps "
            "WHERE role = 'OWNER' AND (capabilities IS NULL OR capabilities = '[]')"
        ).bindparams(caps=OWNER_DEFAULT_CAPABILITIES)
    )


def downgrade() -> None:
    op.execute(sa.text("UPDATE users SET role = 'MANAGER' WHERE role = 'PROJECT_MANAGER'"))
    op.execute(
        sa.text(
            "UPDATE users SET role = 'MEMBER' "
            "WHERE role IN ('DIRECTOR', 'CONTENT_SPECIALIST', 'DESIGNER', 'EDITOR')"
        )
    )
