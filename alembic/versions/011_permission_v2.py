"""
Permission v2: Dual-realm architecture.

- Create source_departments M2M table
- Migrate Source.department_id to source_departments rows
- Drop Source.department_id column
- Update ProjectMember.role to use new WorkspaceRole values
- Drop deprecated tables: knowledge_scopes, scope_memberships
- Migrate Role.permissions to new scoped format

Revision ID: 011_permission_v2
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "011_permission_v2"
down_revision = "010"
branch_labels = None
depends_on = None

# Legacy → new permission mapping
LEGACY_MAP = {
    "documents.read":      ["doc:read:own_dept"],
    "documents.create":    ["doc:create:own_dept"],
    "documents.edit":      ["doc:edit:own_dept"],
    "documents.delete":    ["doc:delete:own_dept"],
    "kb.read":             ["wiki:read:own_dept"],
    "kb.create":           ["wiki:write:own_dept"],
    "kb.edit":             ["wiki:write:own_dept"],
    "kb.delete":           ["wiki:delete:own_dept"],
    "departments.read":    ["org:departments:read"],
    "departments.create":  ["org:departments:manage"],
    "departments.edit":    ["org:departments:manage"],
    "departments.delete":  ["org:departments:manage"],
    "employees.read":      ["org:employees:read"],
    "employees.create":    ["org:employees:manage"],
    "employees.edit":      ["org:employees:manage"],
    "employees.delete":    ["org:employees:manage"],
    "roles.read":          ["org:roles:read"],
    "roles.create":        ["org:roles:manage"],
    "roles.edit":          ["org:roles:manage"],
    "roles.delete":        ["org:roles:manage"],
    "settings.read":       ["org:settings:read"],
    "settings.edit":       ["org:settings:manage"],
    "workspaces.read":     ["workspace:view:all"],
    "workspaces.create":   [],
    "workspaces.edit":     [],
    "workspaces.delete":   [],
    "scopes.read":         [],
    "scopes.manage":       [],
    "audit.read":          ["org:audit:read"],
    "kb.upload":           ["doc:create:own_dept"],
    "kb.manage":           ["doc:read:own_dept", "doc:create:own_dept", "doc:edit:own_dept", "doc:delete:own_dept",
                            "wiki:read:own_dept", "wiki:write:own_dept", "wiki:delete:own_dept"],
    # Contacts (removed in 009)
    "contacts.manage":     [],
    "contacts.read":       [],
    "contacts.create":     [],
    "contacts.edit":       [],
    "contacts.delete":     [],
}


# Workspace role migration: old → new
ROLE_MAP = {
    "owner": "admin",
    "member": "editor",
}


def upgrade():
    # 1. Create source_departments M2M table
    op.create_table(
        "source_departments",
        sa.Column("source_id", UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("department_id", UUID(as_uuid=True), sa.ForeignKey("departments.id", ondelete="CASCADE"), primary_key=True),
    )

    # 2. Migrate existing Source.department_id to source_departments
    conn = op.get_bind()
    # Check if department_id column exists
    result = conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'sources' AND column_name = 'department_id'"
    ))
    if result.fetchone():
        conn.execute(sa.text(
            "INSERT INTO source_departments (source_id, department_id) "
            "SELECT id, department_id FROM sources WHERE department_id IS NOT NULL "
            "ON CONFLICT DO NOTHING"
        ))
        # Drop the old FK + column
        try:
            op.drop_constraint("sources_department_id_fkey", "sources", type_="foreignkey")
        except Exception:
            pass  # May not exist
        try:
            op.drop_column("sources", "department_id")
        except Exception:
            pass  # May not exist

    # 3. Update ProjectMember.role values
    for old_role, new_role in ROLE_MAP.items():
        conn.execute(sa.text(
            f"UPDATE project_members SET role = '{new_role}' WHERE role = '{old_role}'"
        ))

    # 4. Migrate Role.permissions from legacy to new format
    roles = conn.execute(sa.text("SELECT id, permissions FROM roles")).fetchall()
    for role_id, perms in roles:
        if not perms:
            continue
        new_perms = set()
        for p in perms:
            if p in LEGACY_MAP:
                new_perms.update(LEGACY_MAP[p])
            else:
                new_perms.add(p)
        new_perms_list = sorted(new_perms)
        import json
        conn.execute(
            sa.text("UPDATE roles SET permissions = :perms WHERE id = :id"),
            {"perms": json.dumps(new_perms_list), "id": str(role_id)},
        )

    # 5. Drop deprecated tables
    for table in ["knowledge_scopes", "scope_memberships"]:
        try:
            op.drop_table(table)
        except Exception:
            pass  # Table may not exist

    # 6. Update scope_type values in sources/wiki_pages
    # Remove 'department' and 'team' scope types — only 'global' and 'project' remain
    conn.execute(sa.text(
        "UPDATE sources SET scope_type = 'global', scope_id = NULL "
        "WHERE scope_type IN ('department', 'team')"
    ))
    conn.execute(sa.text(
        "UPDATE wiki_pages SET scope_type = 'global', scope_id = NULL "
        "WHERE scope_type IN ('department', 'team')"
    ))


def downgrade():
    # Re-add department_id to sources
    op.add_column("sources", sa.Column("department_id", UUID(as_uuid=True), nullable=True))
    # Best effort: copy first department from M2M
    conn = op.get_bind()
    conn.execute(sa.text(
        "UPDATE sources SET department_id = sd.department_id "
        "FROM (SELECT DISTINCT ON (source_id) source_id, department_id "
        "      FROM source_departments ORDER BY source_id) sd "
        "WHERE sources.id = sd.source_id"
    ))
    op.drop_table("source_departments")
