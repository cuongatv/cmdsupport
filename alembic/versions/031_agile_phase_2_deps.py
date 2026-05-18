"""Agile Phase 2: directed task dependencies (T8).

Revision ID: 031
Revises: 030
Create Date: 2026-05-17

Adds the ``task_dependencies`` table that powers blocked-by/blocks semantics
in the Phase 2 task model. The pair ``(from_task_id, to_task_id)`` is unique
so a duplicate edge surfaces as ``IntegrityError`` even if the application
pre-check races; cycles are rejected by the service layer via a recursive
CTE before the insert lands. ``ON DELETE CASCADE`` on both endpoints means
deleting either task sweeps the edge automatically — no orphan-edge cleanup
job needed.

Additive migration: no existing rows are touched, no columns are altered,
the rollout stays reversible.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_dependencies",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "from_task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "to_task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "dep_type",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'blocks'"),
        ),
        sa.Column(
            "created_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "from_task_id", "to_task_id", name="uq_task_dep_pair"
        ),
        sa.CheckConstraint(
            "from_task_id <> to_task_id",
            name="ck_task_dep_no_self_edge",
        ),
    )
    op.create_index(
        "ix_task_dependencies_from", "task_dependencies", ["from_task_id"]
    )
    op.create_index(
        "ix_task_dependencies_to", "task_dependencies", ["to_task_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_task_dependencies_to", table_name="task_dependencies")
    op.drop_index("ix_task_dependencies_from", table_name="task_dependencies")
    op.drop_table("task_dependencies")
