"""estimated time and weekly capacity (F17)

Adds tasks.estimated_minutes, users.weekly_capacity_hours and the
``reel_estimates`` default setting (handoff §7, §12).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-07
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REEL_ESTIMATES = {"edit_normal_min": 45, "edit_motion_min": 100, "edit_trial_min": 30, "cover_min": 45}

_settings = sa.table(
    "settings",
    sa.column("key", sa.String()),
    sa.column("value", sa.JSON()),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.add_column(sa.Column("estimated_minutes", sa.Integer(), nullable=True))

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("weekly_capacity_hours", sa.Integer(), nullable=True))

    now = datetime.now(UTC)
    op.bulk_insert(
        _settings,
        [{"key": "reel_estimates", "value": REEL_ESTIMATES, "created_at": now, "updated_at": now}],
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM settings WHERE key = 'reel_estimates'"))

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("weekly_capacity_hours")

    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.drop_column("estimated_minutes")
