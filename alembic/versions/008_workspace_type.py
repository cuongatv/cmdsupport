"""Add workspace_type column to projects table.

Revision ID: 008
Revises: 007
Create Date: 2026-05-04
"""

import sqlalchemy as sa

from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "workspace_type",
            sa.String(20),
            server_default="project",
            nullable=False,
            comment="project or customer",
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "workspace_type")
