"""CMD Advisory v2: fingerprint + snapshot + reuse tracking columns.

Revision ID: a1b2c3d4e5f6
Revises: 018
Create Date: 2026-05-11
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cmd_advisory_sessions",
        sa.Column("input_fingerprint", sa.String(64), nullable=True),
    )
    op.add_column(
        "cmd_advisory_sessions",
        sa.Column("source_snapshot_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "cmd_advisory_sessions",
        sa.Column("retrieval_snapshot", JSONB, nullable=True),
    )
    op.add_column(
        "cmd_advisory_sessions",
        sa.Column("reuse_status", sa.String(20), nullable=True),
    )
    op.add_column(
        "cmd_advisory_sessions",
        sa.Column("refresh_reason", sa.Text, nullable=True),
    )
    op.add_column(
        "cmd_advisory_sessions",
        sa.Column("schema_version", sa.String(20), nullable=True),
    )
    op.create_index(
        "cmd_advisory_fingerprint_idx",
        "cmd_advisory_sessions",
        ["input_fingerprint"],
    )


def downgrade() -> None:
    op.drop_index("cmd_advisory_fingerprint_idx", table_name="cmd_advisory_sessions")
    op.drop_column("cmd_advisory_sessions", "schema_version")
    op.drop_column("cmd_advisory_sessions", "refresh_reason")
    op.drop_column("cmd_advisory_sessions", "reuse_status")
    op.drop_column("cmd_advisory_sessions", "retrieval_snapshot")
    op.drop_column("cmd_advisory_sessions", "source_snapshot_hash")
    op.drop_column("cmd_advisory_sessions", "input_fingerprint")
