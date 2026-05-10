"""Add roles table and custom_role_id to employees.

Revision ID: 005
Revises: 004
Create Date: 2026-05-03
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("permissions", JSONB, nullable=False, server_default="[]"),
        sa.Column("is_system", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # Seed system roles
    op.execute("""
        INSERT INTO roles (id, name, description, permissions, is_system)
        VALUES
          (gen_random_uuid(), 'Admin',    'Full access to all features',   '["kb.upload","kb.manage","contacts.manage","departments.manage","employees.manage","projects.manage","settings.manage"]', true),
          (gen_random_uuid(), 'Employee', 'Default — no portal permissions', '[]', true)
    """)

    op.add_column(
        "employees",
        sa.Column(
            "custom_role_id",
            UUID(as_uuid=True),
            sa.ForeignKey("roles.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_employees_custom_role_id", "employees", ["custom_role_id"])


def downgrade() -> None:
    op.drop_index("ix_employees_custom_role_id", table_name="employees")
    op.drop_column("employees", "custom_role_id")
    op.drop_table("roles")
