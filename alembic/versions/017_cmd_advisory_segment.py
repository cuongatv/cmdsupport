"""Add customer_segment to cmd_advisory_sessions.

Revision ID: 017
Revises: 016
Create Date: 2026-05-07
"""

import sqlalchemy as sa
from alembic import op

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cmd_advisory_sessions",
        sa.Column("customer_segment", sa.String(length=30), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cmd_advisory_sessions", "customer_segment")
