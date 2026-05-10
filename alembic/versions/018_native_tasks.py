"""Native task management tables.

Revision ID: 018
Revises: 017
Create Date: 2026-05-09
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_projects",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("identifier", sa.String(10), nullable=False),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "department_id",
            UUID(as_uuid=True),
            sa.ForeignKey("departments.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "created_by_id",
            UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "allow_any_employee",
            sa.Boolean,
            server_default=sa.false(),
            comment="If True, any active employee can be assigned",
        ),
        sa.Column("is_archived", sa.Boolean, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "(workspace_id IS NOT NULL)::int + (department_id IS NOT NULL)::int = 1",
            name="ck_task_project_scope_xor",
        ),
    )
    op.create_index("ix_task_projects_workspace_id", "task_projects", ["workspace_id"])
    op.create_index("ix_task_projects_department_id", "task_projects", ["department_id"])

    op.create_table(
        "task_states",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "task_project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("task_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column(
            "group",
            sa.String(50),
            nullable=False,
            comment="backlog|todo|in_progress|review|done|cancelled",
        ),
        sa.Column("color", sa.String(20), nullable=True),
        sa.Column("position", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("is_default", sa.Boolean, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_task_states_project_id", "task_states", ["task_project_id"])

    op.create_table(
        "tasks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "task_project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("task_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "state_id",
            UUID(as_uuid=True),
            sa.ForeignKey("task_states.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "priority",
            sa.String(20),
            server_default="none",
            comment="none|low|medium|high|urgent",
        ),
        sa.Column(
            "parent_task_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "reporter_id",
            UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_by_id",
            UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "position",
            sa.Float,
            nullable=False,
            server_default="1000.0",
            comment="Fractional position within Kanban state lane",
        ),
        sa.Column(
            "version",
            sa.Integer,
            nullable=False,
            server_default="1",
            comment="Optimistic concurrency version",
        ),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_tasks_project_id", "tasks", ["task_project_id"])
    op.create_index("ix_tasks_state_id", "tasks", ["state_id"])
    op.create_index("ix_tasks_parent_task_id", "tasks", ["parent_task_id"])
    op.create_index("ix_tasks_reporter_id", "tasks", ["reporter_id"])
    op.create_index("ix_tasks_due_date", "tasks", ["due_date"])
    op.create_index("ix_tasks_deleted_at", "tasks", ["deleted_at"])
    op.create_index("ix_tasks_priority", "tasks", ["priority"])

    op.create_table(
        "task_assignees",
        sa.Column(
            "task_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "employee_id",
            UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "task_labels",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "task_project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("task_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("color", sa.String(20), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("task_project_id", "name", name="uq_task_label_project_name"),
    )
    op.create_index("ix_task_labels_project_id", "task_labels", ["task_project_id"])

    op.create_table(
        "task_label_links",
        sa.Column(
            "task_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "label_id",
            UUID(as_uuid=True),
            sa.ForeignKey("task_labels.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "task_comments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "task_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author_id",
            UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("is_edited", sa.Boolean, server_default=sa.false()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_task_comments_task_id", "task_comments", ["task_id"])
    op.create_index("ix_task_comments_author_id", "task_comments", ["author_id"])

    op.create_table(
        "task_attachments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "task_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_by_id",
            UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column(
            "storage_key",
            sa.String(1000),
            nullable=False,
            comment="MinIO/S3 object key — never expose directly",
        ),
        sa.Column("content_type", sa.String(200), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_task_attachments_task_id", "task_attachments", ["task_id"])

    op.create_table(
        "task_activities",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "task_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_id",
            UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "verb",
            sa.String(50),
            nullable=False,
            comment="created|state_changed|assigned|unassigned|commented|attachment_added|attachment_removed|priority_changed|due_date_changed|title_changed|description_changed|label_added|label_removed|archived|restored",
        ),
        sa.Column("field_name", sa.String(100), nullable=True),
        sa.Column("old_value", sa.Text, nullable=True),
        sa.Column("new_value", sa.Text, nullable=True),
        sa.Column("meta", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_task_activities_task_id", "task_activities", ["task_id"])
    op.create_index("ix_task_activities_created_at", "task_activities", ["created_at"])

    op.create_table(
        "notifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "recipient_id",
            UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_id",
            UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "notification_type",
            sa.String(50),
            nullable=False,
            comment="assigned|mentioned|commented|state_changed|due_soon",
        ),
        sa.Column(
            "task_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("body", sa.Text, nullable=True),
        sa.Column("is_read", sa.Boolean, server_default=sa.false()),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_notifications_recipient_id", "notifications", ["recipient_id"])
    op.create_index("ix_notifications_is_read", "notifications", ["is_read"])
    op.create_index("ix_notifications_task_id", "notifications", ["task_id"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("task_activities")
    op.drop_table("task_attachments")
    op.drop_table("task_comments")
    op.drop_table("task_label_links")
    op.drop_table("task_assignees")
    op.drop_table("task_labels")
    op.drop_table("tasks")
    op.drop_table("task_states")
    op.drop_table("task_projects")
