# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportAttributeAccessIssue=false
"""Add wiki page taxonomy classification audit columns.

Revision ID: 038
Revises: 037
Create Date: 2026-05-19

Adds four audit columns to ``wiki_pages`` that describe how the taxonomy
classifier produced the values already stored in
``wiki_pages.knowledge_type_slugs``:

* ``taxonomy_confidence``         — Float in [0.0, 1.0], nullable.
* ``taxonomy_rationale``          — short content-free rationale, nullable.
                                    MUST NOT contain wiki body excerpts.
* ``taxonomy_needs_review``       — Boolean, NOT NULL, server default ``false``.
* ``taxonomy_classifier_version`` — String(20), nullable (e.g. ``"v1"``).

The slug list itself stays in ``knowledge_type_slugs`` — this migration does
not duplicate taxonomy data. Reversible: ``downgrade`` drops the four
columns.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "wiki_pages",
        sa.Column("taxonomy_confidence", sa.Float(), nullable=True),
    )
    op.add_column(
        "wiki_pages",
        sa.Column("taxonomy_rationale", sa.Text(), nullable=True),
    )
    op.add_column(
        "wiki_pages",
        sa.Column(
            "taxonomy_needs_review",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "wiki_pages",
        sa.Column("taxonomy_classifier_version", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("wiki_pages", "taxonomy_classifier_version")
    op.drop_column("wiki_pages", "taxonomy_needs_review")
    op.drop_column("wiki_pages", "taxonomy_rationale")
    op.drop_column("wiki_pages", "taxonomy_confidence")
