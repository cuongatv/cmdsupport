"""
Alembic migration: add progress tracking columns to sources.
"""

import sqlalchemy as sa

from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("progress", sa.Integer(), server_default="0", nullable=False))
    op.add_column("sources", sa.Column("progress_message", sa.String(500), nullable=True))
    op.add_column("sources", sa.Column("job_id", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("sources", "job_id")
    op.drop_column("sources", "progress_message")
    op.drop_column("sources", "progress")
