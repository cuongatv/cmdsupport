"""Add WIP and aging columns to task states.

Revision ID: 029
Revises: 028
Create Date: 2026-05-17
"""

import sqlalchemy as sa

from alembic import op

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "task_states",
        sa.Column("wip_limit", sa.Integer(), nullable=True),
    )
    op.add_column(
        "task_states",
        sa.Column(
            "wip_policy",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'off'"),
        ),
    )
    op.add_column(
        "task_states",
        sa.Column("aging_warn_days", sa.SmallInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("task_states", "aging_warn_days")
    op.drop_column("task_states", "wip_policy")
    op.drop_column("task_states", "wip_limit")
