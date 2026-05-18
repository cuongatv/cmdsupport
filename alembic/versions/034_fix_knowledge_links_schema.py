"""Fix task knowledge link wiki/source schema.

Revision ID: 034
Revises: 033
Create Date: 2026-05-17

Corrects the Phase 4 knowledge-link table without editing the merged 032
migration. Knowledge links may now point at either a compiled wiki page or a
raw source document; both targets are retained as nullable references with
``ON DELETE SET NULL`` so deleting knowledge content does not destroy task
link/audit rows.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "task_knowledge_links",
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_task_knowledge_links_source_id_sources",
        "task_knowledge_links",
        "sources",
        ["source_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_task_knowledge_links_source_id",
        "task_knowledge_links",
        ["source_id"],
    )

    op.drop_constraint(
        "task_knowledge_links_wiki_page_id_fkey",
        "task_knowledge_links",
        type_="foreignkey",
    )
    op.alter_column(
        "task_knowledge_links",
        "wiki_page_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.create_foreign_key(
        "task_knowledge_links_wiki_page_id_fkey",
        "task_knowledge_links",
        "wiki_pages",
        ["wiki_page_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_check_constraint(
        "ck_task_knowledge_links_has_target",
        "task_knowledge_links",
        "wiki_page_id IS NOT NULL OR source_id IS NOT NULL",
    )
    op.execute(
        """
        UPDATE task_knowledge_links
        SET link_type = 'reference'
        WHERE link_type NOT IN ('reference', 'solution', 'blocker', 'related')
        """
    )
    op.create_check_constraint(
        "ck_task_knowledge_links_link_type",
        "task_knowledge_links",
        "link_type IN ('reference', 'solution', 'blocker', 'related')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_task_knowledge_links_link_type",
        "task_knowledge_links",
        type_="check",
    )
    op.drop_constraint(
        "ck_task_knowledge_links_has_target",
        "task_knowledge_links",
        type_="check",
    )

    op.drop_constraint(
        "task_knowledge_links_wiki_page_id_fkey",
        "task_knowledge_links",
        type_="foreignkey",
    )
    op.execute(
        """
        DELETE FROM task_knowledge_links
        WHERE wiki_page_id IS NULL
        """
    )
    op.alter_column(
        "task_knowledge_links",
        "wiki_page_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.create_foreign_key(
        "task_knowledge_links_wiki_page_id_fkey",
        "task_knowledge_links",
        "wiki_pages",
        ["wiki_page_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_index(
        "ix_task_knowledge_links_source_id",
        table_name="task_knowledge_links",
    )
    op.drop_constraint(
        "fk_task_knowledge_links_source_id_sources",
        "task_knowledge_links",
        type_="foreignkey",
    )
    op.drop_column("task_knowledge_links", "source_id")
