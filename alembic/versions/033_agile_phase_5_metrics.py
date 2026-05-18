"""Agile Phase 5: task flow snapshots and metrics.

Revision ID: 033
Revises: 032
Create Date: 2026-05-17

Adds a daily per-project/per-state aggregate table for cumulative-flow style
metrics. The table is additive and idempotent at the DB layer via a unique key
on ``(task_project_id, snapshot_date, state_id)``; application code also checks
before inserting so scheduled jobs can safely retry.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_flow_snapshots",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "task_project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("task_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column(
            "state_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("task_states.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "task_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("story_points_sum", sa.Integer(), nullable=True),
        sa.Column(
            "blocked_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "task_project_id",
            "snapshot_date",
            "state_id",
            name="uq_task_flow_snapshot_project_date_state",
        ),
    )
    op.create_index(
        "ix_task_flow_snapshots_project_date_desc",
        "task_flow_snapshots",
        ["task_project_id", sa.text("snapshot_date DESC")],
    )


def downgrade() -> None:
    op.drop_table("task_flow_snapshots")
