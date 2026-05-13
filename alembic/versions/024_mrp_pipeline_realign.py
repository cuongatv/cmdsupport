"""Realign MRP schema with code models.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-05-13

Migration 023 was overwritten by an interrupted port and created
``mrp_plans`` / ``mrp_artifacts``. The runtime models live in
``app/database/models.py`` as ``SourceChunkExtract`` and
``SourceCompilationPlan`` (tables ``source_chunk_extracts`` and
``source_compilation_plans``). Drop the unused tables and create the
expected ones so the opt-in MRP pipeline works without touching the
legacy ingestion path.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_if_exists(*tables: str) -> None:
    for table in tables:
        op.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')


def upgrade() -> None:
    # Drop unused tables created by the overwritten 023 migration so we can
    # rebuild the schema we actually use. The tables are never populated yet,
    # so no data migration is needed.
    _drop_if_exists("mrp_artifacts", "mrp_plans")

    op.create_table(
        "source_chunk_extracts",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "source_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("start_char", sa.Integer(), nullable=False),
        sa.Column("end_char", sa.Integer(), nullable=False),
        sa.Column("section_path", sa.Text(), nullable=True),
        sa.Column("extract_json", JSONB(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_unique_constraint(
        "uq_sce_source_chunk",
        "source_chunk_extracts",
        ["source_id", "chunk_index"],
    )
    op.create_index(
        "ix_sce_source_status",
        "source_chunk_extracts",
        ["source_id", "status"],
    )

    op.create_table(
        "source_compilation_plans",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "source_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("plan_json", JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="pending_review",
        ),
        sa.Column(
            "reviewed_by",
            UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_scp_status", "source_compilation_plans", ["status"])


def downgrade() -> None:
    op.drop_index("ix_scp_status", table_name="source_compilation_plans")
    op.drop_table("source_compilation_plans")
    op.drop_index("ix_sce_source_status", table_name="source_chunk_extracts")
    op.drop_constraint(
        "uq_sce_source_chunk",
        "source_chunk_extracts",
        type_="unique",
    )
    op.drop_table("source_chunk_extracts")

    # Note: we do not recreate ``mrp_plans`` / ``mrp_artifacts`` on downgrade
    # because the live code never references them.
