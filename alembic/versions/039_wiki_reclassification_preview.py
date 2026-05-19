# pyright: reportMissingImports=false, reportUnknownMemberType=false
"""Persist wiki reclassification previews server-side.

Revision ID: 039
Revises: 038
Create Date: 2026-05-19
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wiki_reclassification_previews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("preview_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["employees.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_wiki_reclassification_previews_created_by",
        "wiki_reclassification_previews",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        "ix_wiki_reclassification_previews_expires_at",
        "wiki_reclassification_previews",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_wiki_reclassification_previews_expires_at",
        table_name="wiki_reclassification_previews",
    )
    op.drop_index(
        "ix_wiki_reclassification_previews_created_by",
        table_name="wiki_reclassification_previews",
    )
    op.drop_table("wiki_reclassification_previews")
