"""Agile Phase 2: sprints, semantics columns on tasks, DoR/DoD templates.

Revision ID: 030
Revises: 029
Create Date: 2026-05-17

Phase 2 is additive: every new column on ``tasks`` is nullable so existing rows
remain valid without a backfill. Sprint membership is opt-in via ``sprint_id``;
the project-level DoR/DoD template is snapshotted into each task at creation
time by the service layer (later template edits never touch existing rows).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ----------------------------------------------------------------- sprints
    # Must exist BEFORE tasks.sprint_id FK is added.
    op.create_table(
        "sprints",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "task_project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("task_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("goal", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'planned'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('planned','active','completed','cancelled')",
            name="ck_sprints_status_valid",
        ),
    )
    op.create_index(
        "ix_sprints_task_project_id",
        "sprints",
        ["task_project_id"],
    )

    # Partial unique index enforces "at most one ACTIVE sprint per project".
    # Built CONCURRENTLY per the Phase 2 spec; CONCURRENTLY cannot run inside
    # a transaction, so we drop into an autocommit block. The sprints table
    # was created above in the outer transaction; autocommit_block commits it
    # first so the new table is visible to the CONCURRENTLY statement.
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "
            "uix_sprints_one_active_per_project "
            "ON sprints(task_project_id) WHERE status = 'active'"
        )

    # ------------------------------------------------------- task semantics
    # All columns are nullable so the migration is safe for existing rows.
    op.add_column(
        "tasks",
        sa.Column("task_type", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column("estimate", sa.String(length=5), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column("story_points", sa.SmallInteger(), nullable=True),
    )
    op.create_check_constraint(
        "ck_tasks_story_points_non_negative",
        "tasks",
        "story_points IS NULL OR story_points >= 0",
    )
    op.add_column(
        "tasks",
        sa.Column("acceptance_criteria", sa.Text(), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column("dor_checklist", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column("dod_checklist", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column("blocked_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column("blocked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "blocked_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    # sprint_id LAST so the FK target table (sprints) already exists.
    op.add_column(
        "tasks",
        sa.Column(
            "sprint_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sprints.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_tasks_sprint_id", "tasks", ["sprint_id"])

    # --------------------------------------------------- DoR/DoD template
    op.create_table(
        "task_project_templates",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "task_project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("task_projects.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "dor_template",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "dod_template",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    # Reverse dependency order: templates first, then tasks.sprint_id (which
    # is the FK to sprints), then the rest of tasks columns, then sprints.
    op.drop_table("task_project_templates")

    op.drop_index("ix_tasks_sprint_id", table_name="tasks")
    op.drop_column("tasks", "sprint_id")
    op.drop_column("tasks", "blocked_by_id")
    op.drop_column("tasks", "blocked_at")
    op.drop_column("tasks", "blocked_reason")
    op.drop_column("tasks", "dod_checklist")
    op.drop_column("tasks", "dor_checklist")
    op.drop_column("tasks", "acceptance_criteria")
    op.drop_constraint(
        "ck_tasks_story_points_non_negative", "tasks", type_="check"
    )
    op.drop_column("tasks", "story_points")
    op.drop_column("tasks", "estimate")
    op.drop_column("tasks", "task_type")

    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS uix_sprints_one_active_per_project"
        )
    op.drop_index("ix_sprints_task_project_id", table_name="sprints")
    op.drop_table("sprints")
