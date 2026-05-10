"""Scope-based RBAC: scope_memberships, audit_log, scope columns on sources/wiki_pages.

Revision ID: 007
Revises: 006
Create Date: 2026-05-04
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- scope_memberships ---
    op.create_table(
        "scope_memberships",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("employee_id", UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scope_type", sa.String(20), nullable=False, comment="global, project, department, team"),
        sa.Column("scope_id", UUID(as_uuid=True), nullable=True, comment="Scope entity ID. Null for global scope."),
        sa.Column("role", sa.String(20), nullable=False, server_default="reader", comment="reader, contributor, owner, admin"),
        sa.Column("granted_by_id", UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_scope_memberships_employee_id", "scope_memberships", ["employee_id"])
    op.create_index("ix_scope_memberships_scope", "scope_memberships", ["scope_type", "scope_id"])
    op.create_unique_constraint(
        "uq_scope_membership_employee_scope",
        "scope_memberships",
        ["employee_id", "scope_type", "scope_id"],
    )

    # --- audit_log ---
    op.create_table(
        "audit_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("principal_id", UUID(as_uuid=True), nullable=False, comment="Employee or agent ID"),
        sa.Column("principal_type", sa.String(20), server_default="human", nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.String(100), nullable=False),
        sa.Column("scope_type", sa.String(20), nullable=True),
        sa.Column("scope_id", UUID(as_uuid=True), nullable=True),
        sa.Column("decision", sa.String(10), nullable=False, comment="allow or deny"),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
    )
    op.create_index("ix_audit_log_timestamp", "audit_log", ["timestamp"])
    op.create_index("ix_audit_log_principal", "audit_log", ["principal_id"])
    op.create_index("ix_audit_log_resource", "audit_log", ["resource_type", "resource_id"])

    # --- sources: add scope columns ---
    op.add_column("sources", sa.Column("scope_type", sa.String(20), server_default="global"))
    op.add_column("sources", sa.Column("scope_id", UUID(as_uuid=True), nullable=True))

    # --- wiki_pages: add scope columns ---
    op.add_column("wiki_pages", sa.Column("scope_type", sa.String(20), server_default="global"))
    op.add_column("wiki_pages", sa.Column("scope_id", UUID(as_uuid=True), nullable=True))

    # --- Data migration: seed scope_memberships from existing data ---

    # 1. Every admin employee → global admin
    op.execute("""
        INSERT INTO scope_memberships (employee_id, scope_type, scope_id, role)
        SELECT id, 'global', NULL, 'admin'
        FROM employees
        WHERE role = 'admin' AND is_active = true
        ON CONFLICT DO NOTHING
    """)

    # 2. Every non-admin active employee → global reader
    op.execute("""
        INSERT INTO scope_memberships (employee_id, scope_type, scope_id, role)
        SELECT id, 'global', NULL, 'reader'
        FROM employees
        WHERE role != 'admin' AND is_active = true
        ON CONFLICT DO NOTHING
    """)

    # 3. Every employee → contributor in their department
    op.execute("""
        INSERT INTO scope_memberships (employee_id, scope_type, scope_id, role)
        SELECT id, 'department', department_id, 'contributor'
        FROM employees
        WHERE department_id IS NOT NULL AND is_active = true
        ON CONFLICT DO NOTHING
    """)

    # 4. Project members → scope memberships
    #    owner → owner, member → contributor
    op.execute("""
        INSERT INTO scope_memberships (employee_id, scope_type, scope_id, role)
        SELECT
            pm.employee_id,
            'project',
            pm.project_id,
            CASE WHEN pm.role = 'owner' THEN 'owner' ELSE 'contributor' END
        FROM project_members pm
        JOIN employees e ON e.id = pm.employee_id AND e.is_active = true
        ON CONFLICT DO NOTHING
    """)

    # 5. Set existing sources scope to department if they have a department_id
    op.execute("""
        UPDATE sources
        SET scope_type = 'department', scope_id = department_id
        WHERE department_id IS NOT NULL
    """)


def downgrade() -> None:
    # Remove scope columns from wiki_pages
    op.drop_column("wiki_pages", "scope_id")
    op.drop_column("wiki_pages", "scope_type")

    # Remove scope columns from sources
    op.drop_column("sources", "scope_id")
    op.drop_column("sources", "scope_type")

    # Drop audit_log
    op.drop_index("ix_audit_log_resource", table_name="audit_log")
    op.drop_index("ix_audit_log_principal", table_name="audit_log")
    op.drop_index("ix_audit_log_timestamp", table_name="audit_log")
    op.drop_table("audit_log")

    # Drop scope_memberships
    op.drop_constraint("uq_scope_membership_employee_scope", "scope_memberships")
    op.drop_index("ix_scope_memberships_scope", table_name="scope_memberships")
    op.drop_index("ix_scope_memberships_employee_id", table_name="scope_memberships")
    op.drop_table("scope_memberships")
