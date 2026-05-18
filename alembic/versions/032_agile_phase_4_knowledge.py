"""Agile Phase 4: task ↔ wiki page knowledge links (T15).

Revision ID: 032
Revises: 031
Create Date: 2026-05-17

Adds the ``task_knowledge_links`` table that lets a task reference one or
more wiki pages with a typed relationship (``reference`` / ``requirement``
/ ``solution``). The pair ``(task_id, wiki_page_id)`` is unique so a
duplicate insert surfaces as ``IntegrityError`` even if the application
pre-check races; the service layer translates that into the stable
``DUPLICATE_KNOWLEDGE_LINK`` error code.

``ON DELETE CASCADE`` on both FK ends means deleting either the task or
the wiki page sweeps the link automatically — no orphan-row cleanup job
is needed. ``created_by_id`` is nullable + ``ON DELETE SET NULL`` so
removing the linking employee does not destroy the audit trail of which
links exist.

Additive migration: no existing rows are touched, no columns are altered,
the rollout stays reversible.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_knowledge_links",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "wiki_page_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("wiki_pages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "link_type",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'reference'"),
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
            "task_id", "wiki_page_id", name="uq_task_knowledge_link_pair"
        ),
    )
    op.create_index(
        "ix_task_knowledge_links_task_id",
        "task_knowledge_links",
        ["task_id"],
    )
    op.create_index(
        "ix_task_knowledge_links_wiki_page_id",
        "task_knowledge_links",
        ["wiki_page_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_task_knowledge_links_wiki_page_id",
        table_name="task_knowledge_links",
    )
    op.drop_index(
        "ix_task_knowledge_links_task_id",
        table_name="task_knowledge_links",
    )
    op.drop_table("task_knowledge_links")
