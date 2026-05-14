"""Add personal project scheduling habits.

Revision ID: 027
Revises: b8c9d0e1f2a3
Create Date: 2026-05-14
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID

from alembic import op

revision = "027"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


TASK_PRIORITY_VALUES = ("none", "low", "medium", "high", "urgent")
HABIT_OCCURRENCE_STATUS_VALUES = ("completed", "skipped", "shifted")


task_priority_enum = ENUM(
    *TASK_PRIORITY_VALUES,
    name="task_priority_enum",
    create_type=False,
)
habit_occurrence_status_enum = ENUM(
    *HABIT_OCCURRENCE_STATUS_VALUES,
    name="habit_occurrence_status_enum",
    create_type=False,
)


def upgrade() -> None:
    op.execute(
        "CREATE TYPE task_priority_enum AS ENUM "
        "('none', 'low', 'medium', 'high', 'urgent')"
    )
    op.execute(
        "CREATE TYPE habit_occurrence_status_enum AS ENUM "
        "('completed', 'skipped', 'shifted')"
    )

    op.add_column(
        "task_projects",
        sa.Column("owner_employee_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "task_projects_owner_employee_id_fkey",
        "task_projects",
        "employees",
        ["owner_employee_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "ck_task_project_scope_xor",
        "task_projects",
        type_="check",
    )
    op.create_check_constraint(
        "ck_task_project_scope_xor",
        "task_projects",
        "(workspace_id IS NOT NULL)::int + "
        "(department_id IS NOT NULL)::int + "
        "(owner_employee_id IS NOT NULL)::int = 1",
    )
    op.create_index(
        "ix_task_projects_owner_employee_id",
        "task_projects",
        ["owner_employee_id"],
    )

    op.add_column(
        "tasks",
        sa.Column("scheduled_start_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column("scheduled_end_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "schedule_locked",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index("ix_tasks_scheduled_start_at", "tasks", ["scheduled_start_at"])

    op.create_table(
        "personal_habits",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_employee_id", UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column(
            "priority",
            task_priority_enum,
            nullable=False,
            server_default="none",
        ),
        sa.Column("preferred_time", sa.Time(), nullable=False),
        sa.Column("duration_minutes", sa.Integer, nullable=False),
        sa.Column("active_days", JSONB, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "duration_minutes >= 1",
            name="ck_personal_habits_duration_minutes_positive",
        ),
        sa.ForeignKeyConstraint(
            ["owner_employee_id"],
            ["employees.id"],
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_personal_habits_owner_employee_id",
        "personal_habits",
        ["owner_employee_id"],
    )
    op.create_index("ix_personal_habits_is_active", "personal_habits", ["is_active"])

    op.create_table(
        "habit_occurrence_states",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("habit_id", UUID(as_uuid=True), nullable=False),
        sa.Column("occurrence_date", sa.Date(), nullable=False),
        sa.Column("state", habit_occurrence_status_enum, nullable=False),
        sa.Column("actual_start", sa.Time(), nullable=True),
        sa.Column("shift_reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["habit_id"],
            ["personal_habits.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "habit_id",
            "occurrence_date",
            name="uq_habit_occurrence_state_habit_date",
        ),
    )
    op.create_index(
        "ix_habit_occurrence_states_habit_id",
        "habit_occurrence_states",
        ["habit_id"],
    )
    op.create_index(
        "ix_habit_occurrence_states_occurrence_date",
        "habit_occurrence_states",
        ["occurrence_date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_habit_occurrence_states_occurrence_date",
        table_name="habit_occurrence_states",
    )
    op.drop_index(
        "ix_habit_occurrence_states_habit_id",
        table_name="habit_occurrence_states",
    )
    op.drop_table("habit_occurrence_states")

    op.drop_index("ix_personal_habits_is_active", table_name="personal_habits")
    op.drop_index(
        "ix_personal_habits_owner_employee_id",
        table_name="personal_habits",
    )
    op.drop_table("personal_habits")

    op.drop_index("ix_tasks_scheduled_start_at", table_name="tasks")
    op.drop_column("tasks", "schedule_locked")
    op.drop_column("tasks", "scheduled_end_at")
    op.drop_column("tasks", "scheduled_start_at")
    op.drop_index("ix_task_projects_owner_employee_id", table_name="task_projects")
    op.execute("DELETE FROM task_projects WHERE owner_employee_id IS NOT NULL")
    op.drop_constraint(
        "ck_task_project_scope_xor",
        "task_projects",
        type_="check",
    )
    op.create_check_constraint(
        "ck_task_project_scope_xor",
        "task_projects",
        "(workspace_id IS NOT NULL)::int + (department_id IS NOT NULL)::int = 1",
    )
    op.drop_constraint(
        "task_projects_owner_employee_id_fkey",
        "task_projects",
        type_="foreignkey",
    )
    op.drop_column("task_projects", "owner_employee_id")

    op.execute("DROP TYPE habit_occurrence_status_enum")
    op.execute("DROP TYPE task_priority_enum")
