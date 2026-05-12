"""Add profile fields to employees: phone, zalo_phone, avatar_key, slogan.

Adds columns supporting the user-creation form on /admin/employees:
- phone: primary phone number
- zalo_phone: Zalo number; falls back to `phone` at read time when empty
- avatar_key: object-storage key for the avatar image (jpg/jpeg/png/webp)
- slogan: free-text motto

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-12
"""

import sqlalchemy as sa

from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "employees",
        sa.Column("phone", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "employees",
        sa.Column("zalo_phone", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "employees",
        sa.Column("avatar_key", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "employees",
        sa.Column("slogan", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("employees", "slogan")
    op.drop_column("employees", "avatar_key")
    op.drop_column("employees", "zalo_phone")
    op.drop_column("employees", "phone")
