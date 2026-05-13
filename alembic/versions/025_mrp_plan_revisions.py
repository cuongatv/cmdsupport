"""MRP plan revision history.

Adds:
- source_compilation_plans.version (int, default 1)
- source_compilation_plan_revisions table (feedback history + status)

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-05-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "source_compilation_plans",
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )

    op.create_table(
        "source_compilation_plan_revisions",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "plan_id",
            UUID(as_uuid=True),
            sa.ForeignKey("source_compilation_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "requested_by",
            UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("feedback", sa.Text(), nullable=False),
        sa.Column("base_version", sa.Integer(), nullable=False),
        sa.Column("previous_plan_snapshot", JSONB(), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="requested",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_scp_revision_plan",
        "source_compilation_plan_revisions",
        ["plan_id"],
    )
    op.create_index(
        "ix_scp_revision_source_status",
        "source_compilation_plan_revisions",
        ["source_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scp_revision_source_status",
        table_name="source_compilation_plan_revisions",
    )
    op.drop_index(
        "ix_scp_revision_plan",
        table_name="source_compilation_plan_revisions",
    )
    op.drop_table("source_compilation_plan_revisions")
    op.drop_column("source_compilation_plans", "version")
