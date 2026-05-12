"""Province <-> Employee assignment for HQ contact officer.

Adds `provinces.assigned_employee_id` so each Vietnamese province/city can be
mapped to a single HQ employee. Powers two surfaces:

- Admin "Thông tin phụ trách Chi nhánh" tab under Menu Tổ chức.
- "CÁN BỘ ĐẦU MỐI TẠI TRỤ SỞ CHÍNH" section at the bottom of every CMD
  advisory result.

ON DELETE SET NULL keeps the province row when its assignee is removed so
admins can re-assign without losing province data.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-12
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "provinces",
        sa.Column("assigned_employee_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_provinces_assigned_employee_id_employees",
        "provinces",
        "employees",
        ["assigned_employee_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_provinces_assigned_employee_id",
        "provinces",
        ["assigned_employee_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_provinces_assigned_employee_id", table_name="provinces")
    op.drop_constraint(
        "fk_provinces_assigned_employee_id_employees",
        "provinces",
        type_="foreignkey",
    )
    op.drop_column("provinces", "assigned_employee_id")
