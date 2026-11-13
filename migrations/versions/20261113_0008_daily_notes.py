"""daily notes for the daily operations report (M7)

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-13 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0008'
down_revision: str | None = '0007'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('daily_notes',
    sa.Column('report_date', sa.Date(), nullable=False),
    sa.Column('author_id', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], name=op.f('fk_daily_notes_author_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_daily_notes'))
    )
    with op.batch_alter_table('daily_notes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_daily_notes_report_date'), ['report_date'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('daily_notes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_daily_notes_report_date'))
    op.drop_table('daily_notes')
