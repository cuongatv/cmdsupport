"""Opt-in MRP ingestion pipeline schema.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-13
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column(
            "pipeline_strategy",
            sa.String(50),
            nullable=True,
            comment="MRP triage strategy for opt-in ingestion, e.g. map_reduce or refine",
        ),
    )
    op.add_column(
        "sources",
        sa.Column(
            "pipeline_phase",
            sa.String(50),
            nullable=True,
            comment="Current MRP pipeline phase for opt-in ingestion",
        ),
    )

    op.create_table(
        "mrp_plans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("strategy", sa.String(50), nullable=False, server_default="map_reduce"),
        sa.Column("plan_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "approved_by_id",
            UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "rejected_by_id",
            UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_mrp_plans_source_id", "mrp_plans", ["source_id"])
    op.create_index("ix_mrp_plans_status", "mrp_plans", ["status"])

    op.create_table(
        "mrp_artifacts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("phase", sa.String(50), nullable=False),
        sa.Column("artifact_type", sa.String(50), nullable=False),
        sa.Column("sequence", sa.Integer, nullable=False, server_default="0"),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_mrp_artifacts_source_phase",
        "mrp_artifacts",
        ["source_id", "phase"],
    )
    op.create_index(
        "ix_mrp_artifacts_source_type",
        "mrp_artifacts",
        ["source_id", "artifact_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_mrp_artifacts_source_type", table_name="mrp_artifacts")
    op.drop_index("ix_mrp_artifacts_source_phase", table_name="mrp_artifacts")
    op.drop_table("mrp_artifacts")

    op.drop_index("ix_mrp_plans_status", table_name="mrp_plans")
    op.drop_index("ix_mrp_plans_source_id", table_name="mrp_plans")
    op.drop_table("mrp_plans")

    op.drop_column("sources", "pipeline_phase")
    op.drop_column("sources", "pipeline_strategy")
