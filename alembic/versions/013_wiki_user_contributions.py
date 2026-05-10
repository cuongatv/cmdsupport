"""Add user contribution columns to wiki_pages.

Revision ID: 013
Revises: 012
Create Date: 2026-05-06
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("wiki_pages", sa.Column("user_contribution_md", sa.Text, nullable=True))
    op.add_column(
        "wiki_pages",
        sa.Column(
            "contributed_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("wiki_pages", sa.Column("contributed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("wiki_pages", sa.Column("contribution_note", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("wiki_pages", "contribution_note")
    op.drop_column("wiki_pages", "contributed_at")
    op.drop_column("wiki_pages", "contributed_by_id")
    op.drop_column("wiki_pages", "user_contribution_md")
