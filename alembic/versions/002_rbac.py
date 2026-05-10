"""Add RBAC, Knowledge Types, and dynamic scopes

Revision ID: 002_rbac
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from alembic import op

# revision identifiers
revision = '002_rbac'
down_revision = '002'  # depends on 002_add_progress
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Knowledge Types table (admin-defined)
    op.create_table(
        'knowledge_types',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('slug', sa.String(50), nullable=False, unique=True, comment='URL-safe identifier'),
        sa.Column('name', sa.String(100), nullable=False, comment='Display name'),
        sa.Column('color', sa.String(20), server_default='#6366f1', comment='Hex color for UI'),
        sa.Column('description', sa.Text),
        sa.Column('sort_order', sa.Integer, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # 2. Departments table
    op.create_table(
        'departments',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(200), nullable=False, unique=True),
        sa.Column('description', sa.Text),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # 3. Employees table
    op.create_table(
        'employees',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('email', sa.String(200), unique=True, nullable=False),
        sa.Column('password_hash', sa.String(500), comment='bcrypt hash'),
        sa.Column('role', sa.String(20), server_default='employee', comment='admin or employee'),
        sa.Column('department_id', UUID(as_uuid=True), sa.ForeignKey('departments.id', ondelete='CASCADE'), nullable=False),
        sa.Column('mcp_token', sa.String(500), unique=True, comment='Bearer token for MCP'),
        sa.Column('is_active', sa.Boolean, default=True, server_default=sa.text('true')),
        sa.Column('last_connected', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_employees_mcp_token', 'employees', ['mcp_token'])
    op.create_index('ix_employees_department_id', 'employees', ['department_id'])
    op.create_index('ix_employees_email', 'employees', ['email'])

    # 4. Knowledge scopes
    op.create_table(
        'knowledge_scopes',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('department_id', UUID(as_uuid=True), sa.ForeignKey('departments.id', ondelete='CASCADE'), nullable=True),
        sa.Column('employee_id', UUID(as_uuid=True), sa.ForeignKey('employees.id', ondelete='CASCADE'), nullable=True),
        sa.Column('scope_type', sa.String(20), server_default='grant', comment='grant or deny'),
        sa.Column('knowledge_types', ARRAY(sa.String), comment='Filter by KnowledgeType slugs'),
        sa.Column('source_ids', JSONB, comment='Specific source UUIDs'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # 5. Add knowledge_type_id + department_id to sources
    op.add_column('sources', sa.Column(
        'knowledge_type_id', UUID(as_uuid=True),
        sa.ForeignKey('knowledge_types.id', ondelete='SET NULL'),
        nullable=True,
    ))
    op.add_column('sources', sa.Column(
        'department_id', UUID(as_uuid=True),
        sa.ForeignKey('departments.id', ondelete='SET NULL'),
        nullable=True,
    ))

    # 6. Add department_id to contacts
    op.add_column('contacts', sa.Column(
        'department_id', UUID(as_uuid=True),
        sa.ForeignKey('departments.id', ondelete='SET NULL'),
        nullable=True,
    ))

    # 7. Remove old knowledge_type string column if it exists
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE sources DROP COLUMN IF EXISTS knowledge_type;
        EXCEPTION WHEN OTHERS THEN NULL;
        END $$;
    """)

    # 8. Drop old channel tables if they exist
    op.execute("DROP TABLE IF EXISTS chat_messages CASCADE")
    op.execute("DROP TABLE IF EXISTS chat_sessions CASCADE")
    op.execute("DROP TABLE IF EXISTS channel_users CASCADE")

    # 9. Seed default knowledge types
    op.execute("""
        INSERT INTO knowledge_types (slug, name, color, sort_order, description) VALUES
        ('general', 'General', '#6B7280', 0, 'General documents and policies'),
        ('sop', 'SOP', '#10B981', 1, 'Standard Operating Procedures'),
        ('product', 'Product', '#8B5CF6', 2, 'Product specifications and catalogs'),
        ('project', 'Project', '#F59E0B', 3, 'Project documentation'),
        ('customer', 'Customer', '#3B82F6', 4, 'Customer information and case studies')
    """)

    # NOTE: Default admin account is created on first app startup
    # from DEFAULT_ADMIN_EMAIL / DEFAULT_ADMIN_PASSWORD in .env


def downgrade() -> None:
    op.drop_column('contacts', 'department_id')
    op.drop_column('sources', 'department_id')
    op.drop_column('sources', 'knowledge_type_id')
    op.drop_table('knowledge_scopes')
    op.drop_table('employees')
    op.drop_table('departments')
    op.drop_table('knowledge_types')
