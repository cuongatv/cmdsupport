"""Add wiki_page_drafts, wiki_page_revisions; remove old contribution columns.

Revision ID: 014
Revises: 013
Create Date: 2026-05-06
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Remove old single-column contribution approach from wiki_pages
    op.drop_column("wiki_pages", "user_contribution_md")
    op.drop_column("wiki_pages", "contributed_by_id")
    op.drop_column("wiki_pages", "contributed_at")
    op.drop_column("wiki_pages", "contribution_note")

    # 2. Add orphaned flag
    op.add_column(
        "wiki_pages",
        sa.Column("orphaned", sa.Boolean, nullable=False, server_default="false"),
    )

    # 3. Draft table — pending contributions awaiting editor review
    op.create_table(
        "wiki_page_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "page_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("wiki_pages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("content_md", sa.Text, nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("source", sa.String(40), nullable=False, server_default="web_ui"),
        sa.Column("source_metadata", postgresql.JSONB, nullable=True),
        sa.Column(
            "reviewed_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewer_note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_wiki_drafts_page_id", "wiki_page_drafts", ["page_id"])
    op.create_index("ix_wiki_drafts_status", "wiki_page_drafts", ["status"])
    op.create_index("ix_wiki_drafts_author_id", "wiki_page_drafts", ["author_id"])

    # 4. Revision history — full snapshot on every content change
    op.create_table(
        "wiki_page_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "page_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("wiki_pages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("content_md", sa.Text, nullable=False),
        sa.Column("change_type", sa.String(30), nullable=False),
        # agent_compile | agent_retry | editor_edit | draft_approved | manual_rebuild | rollback
        sa.Column(
            "draft_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("wiki_page_drafts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "changed_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("change_note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_wiki_revisions_page_id", "wiki_page_revisions", ["page_id"])
    op.create_index("ix_wiki_revisions_page_version", "wiki_page_revisions", ["page_id", "version"])


def downgrade() -> None:
    op.drop_index("ix_wiki_revisions_page_version", table_name="wiki_page_revisions")
    op.drop_index("ix_wiki_revisions_page_id", table_name="wiki_page_revisions")
    op.drop_table("wiki_page_revisions")

    op.drop_index("ix_wiki_drafts_author_id", table_name="wiki_page_drafts")
    op.drop_index("ix_wiki_drafts_status", table_name="wiki_page_drafts")
    op.drop_index("ix_wiki_drafts_page_id", table_name="wiki_page_drafts")
    op.drop_table("wiki_page_drafts")

    op.drop_column("wiki_pages", "orphaned")

    op.add_column("wiki_pages", sa.Column("contribution_note", sa.Text, nullable=True))
    op.add_column("wiki_pages", sa.Column("contributed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "wiki_pages",
        sa.Column(
            "contributed_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("wiki_pages", sa.Column("user_contribution_md", sa.Text, nullable=True))
