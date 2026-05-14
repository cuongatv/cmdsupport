"""Multi-unit employee memberships.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-05-13
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM, UUID

from alembic import op

revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


UNIT_TYPE_VALUES = ("business_group", "squad_team")
MEMBERSHIP_ROLE_VALUES = (
    "lead",
    "deputy_lead",
    "controller",
    "member",
    "product_owner",
    "scrum_master",
    "developer",
)


unit_type_enum = ENUM(
    *UNIT_TYPE_VALUES,
    name="unit_type_enum",
    create_type=False,
)
membership_role_enum = ENUM(
    *MEMBERSHIP_ROLE_VALUES,
    name="membership_role_enum",
    create_type=False,
)


def upgrade() -> None:
    op.execute("CREATE TYPE unit_type_enum AS ENUM ('business_group', 'squad_team')")
    op.execute(
        """
        CREATE TYPE membership_role_enum AS ENUM (
            'lead', 'deputy_lead', 'controller', 'member',
            'product_owner', 'scrum_master', 'developer'
        )
        """
    )

    op.add_column(
        "departments",
        sa.Column(
            "unit_type",
            unit_type_enum,
            nullable=False,
            server_default="business_group",
        ),
    )
    op.add_column(
        "departments",
        sa.Column("is_archived", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "departments",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.drop_constraint("employees_department_id_fkey", "employees", type_="foreignkey")
    op.create_foreign_key(
        "employees_department_id_fkey",
        "employees",
        "departments",
        ["department_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_table(
        "employee_department_memberships",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "employee_id",
            UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "department_id",
            UUID(as_uuid=True),
            sa.ForeignKey("departments.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("role", membership_role_enum, nullable=False),
        sa.Column("capacity_percent", sa.SmallInteger, nullable=True),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "active_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("active_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "capacity_percent IS NULL OR capacity_percent BETWEEN 0 AND 100",
            name="ck_membership_capacity_percent_range",
        ),
        sa.UniqueConstraint(
            "employee_id",
            "department_id",
            name="uq_membership_employee_department",
        ),
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_membership_primary
        ON employee_department_memberships (employee_id)
        WHERE is_primary = true AND is_active = true
        """
    )
    op.create_index(
        "ix_membership_employee_active",
        "employee_department_memberships",
        ["employee_id", "is_active"],
    )
    op.create_index(
        "ix_membership_department_active",
        "employee_department_memberships",
        ["department_id", "is_active"],
    )
    op.create_index(
        "ix_membership_employee_primary",
        "employee_department_memberships",
        ["employee_id", "is_primary"],
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION fn_validate_membership_role_unit_type()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            v_unit_type text;
            squad_only_roles text[] := ARRAY['product_owner', 'scrum_master', 'developer'];
        BEGIN
            SELECT unit_type INTO v_unit_type FROM departments WHERE id = NEW.department_id;
            IF NEW.role::text = ANY(squad_only_roles) AND v_unit_type != 'squad_team' THEN
                RAISE EXCEPTION 'role % not allowed for unit_type %', NEW.role, v_unit_type;
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_validate_membership_role_unit_type
            BEFORE INSERT OR UPDATE ON employee_department_memberships
            FOR EACH ROW EXECUTE FUNCTION fn_validate_membership_role_unit_type();
        """
    )

    op.execute(
        """
        INSERT INTO employee_department_memberships
            (id, employee_id, department_id, role, is_primary, is_active, active_from)
        SELECT
            gen_random_uuid(),
            id,
            department_id,
            'member'::membership_role_enum,
            true,
            true,
            now()
        FROM employees
        WHERE department_id IS NOT NULL
        ON CONFLICT (employee_id, department_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_validate_membership_role_unit_type
        ON employee_department_memberships
        """
    )
    op.execute("DROP FUNCTION IF EXISTS fn_validate_membership_role_unit_type()")
    # Dropping the membership table removes all backfilled membership rows.
    op.drop_table("employee_department_memberships")

    op.drop_constraint("employees_department_id_fkey", "employees", type_="foreignkey")
    op.create_foreign_key(
        "employees_department_id_fkey",
        "employees",
        "departments",
        ["department_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_column("departments", "archived_at")
    op.drop_column("departments", "is_archived")
    op.drop_column("departments", "unit_type")

    op.execute("DROP TYPE membership_role_enum")
    op.execute("DROP TYPE unit_type_enum")
