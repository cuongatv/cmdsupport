# pyright: reportMissingImports=false, reportUnknownMemberType=false
"""Telegram integration: group bindings, identities, update log, task links, outbox.

Revision ID: 040
Revises: 039
Create Date: 2026-05-20
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # telegram_group_bindings
    # ------------------------------------------------------------------
    op.create_table(
        "telegram_group_bindings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("department_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "default_task_project_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("message_thread_id", sa.BigInteger(), nullable=True),
        sa.Column("chat_title", sa.Text(), nullable=True),
        sa.Column("chat_type", sa.Text(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "bot_status",
            sa.Text(),
            nullable=True,
            comment="Telegram bot membership status: member|kicked|left|migrated",
        ),
        sa.Column("migrated_to_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("bind_code", sa.Text(), nullable=True),
        sa.Column("bind_code_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bound_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("bound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["default_task_project_id"],
            ["task_projects.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["bound_by_id"],
            ["employees.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_telegram_group_bindings_department_id",
        "telegram_group_bindings",
        ["department_id"],
        unique=False,
    )
    op.create_index(
        "ix_telegram_group_bindings_chat_id",
        "telegram_group_bindings",
        ["chat_id"],
        unique=False,
    )
    # COALESCE-based partial unique index requires raw SQL.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_telegram_active_binding
        ON telegram_group_bindings (chat_id, COALESCE(message_thread_id, -1))
        WHERE is_active = true
        """
    )

    # ------------------------------------------------------------------
    # telegram_identities
    # ------------------------------------------------------------------
    op.create_table(
        "telegram_identities",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_username", sa.Text(), nullable=True),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("link_code", sa.Text(), nullable=True),
        sa.Column("link_code_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_telegram_identities_employee_id",
        "telegram_identities",
        ["employee_id"],
        unique=False,
    )
    op.create_index(
        "ix_telegram_identities_telegram_user_id",
        "telegram_identities",
        ["telegram_user_id"],
        unique=False,
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_telegram_active_identity
        ON telegram_identities (telegram_user_id)
        WHERE is_active = true
        """
    )

    # ------------------------------------------------------------------
    # telegram_update_log
    # ------------------------------------------------------------------
    op.create_table(
        "telegram_update_log",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("update_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=True),
        sa.Column("message_thread_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("command", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'pending'"),
            comment="pending|processed|duplicate|failed|ignored",
        ),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("binding_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("identity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "sanitized_meta",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["binding_id"],
            ["telegram_group_bindings.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["identity_id"],
            ["telegram_identities.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("update_id", name="uq_telegram_update_log_update_id"),
    )
    op.create_index(
        "ix_telegram_update_log_chat_received",
        "telegram_update_log",
        ["chat_id", sa.text("received_at DESC")],
        unique=False,
    )

    # ------------------------------------------------------------------
    # telegram_task_links
    # ------------------------------------------------------------------
    op.create_table(
        "telegram_task_links",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("binding_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("origin_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("origin_message_id", sa.BigInteger(), nullable=True),
        sa.Column("origin_message_thread_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_by_identity_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["binding_id"],
            ["telegram_group_bindings.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_identity_id"],
            ["telegram_identities.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_telegram_task_links_task_id",
        "telegram_task_links",
        ["task_id"],
        unique=False,
    )
    op.create_index(
        "ix_telegram_task_links_binding_id",
        "telegram_task_links",
        ["binding_id"],
        unique=False,
    )

    # ------------------------------------------------------------------
    # telegram_outbox
    # ------------------------------------------------------------------
    op.create_table(
        "telegram_outbox",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("binding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "message_kind",
            sa.Text(),
            nullable=False,
            comment=(
                "task_created|task_updated|comment_added|status_changed|"
                "bind_reply|link_reply|error_reply"
            ),
        ),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'pending'"),
            comment="pending|sending|sent|failed|cancelled",
        ),
        sa.Column(
            "retry_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["binding_id"],
            ["telegram_group_bindings.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_telegram_outbox_idempotency_key",
        "telegram_outbox",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_telegram_outbox_status_next_attempt",
        "telegram_outbox",
        ["status", "next_attempt_at"],
        unique=False,
    )
    op.create_index(
        "ix_telegram_outbox_binding_id",
        "telegram_outbox",
        ["binding_id"],
        unique=False,
    )


def downgrade() -> None:
    # telegram_outbox
    op.drop_index(
        "ix_telegram_outbox_binding_id",
        table_name="telegram_outbox",
    )
    op.drop_index(
        "ix_telegram_outbox_status_next_attempt",
        table_name="telegram_outbox",
    )
    op.drop_index(
        "uq_telegram_outbox_idempotency_key",
        table_name="telegram_outbox",
    )
    op.drop_table("telegram_outbox")

    # telegram_task_links
    op.drop_index(
        "ix_telegram_task_links_binding_id",
        table_name="telegram_task_links",
    )
    op.drop_index(
        "ix_telegram_task_links_task_id",
        table_name="telegram_task_links",
    )
    op.drop_table("telegram_task_links")

    # telegram_update_log
    op.drop_index(
        "ix_telegram_update_log_chat_received",
        table_name="telegram_update_log",
    )
    op.drop_table("telegram_update_log")

    # telegram_identities
    op.execute("DROP INDEX IF EXISTS uq_telegram_active_identity")
    op.drop_index(
        "ix_telegram_identities_telegram_user_id",
        table_name="telegram_identities",
    )
    op.drop_index(
        "ix_telegram_identities_employee_id",
        table_name="telegram_identities",
    )
    op.drop_table("telegram_identities")

    # telegram_group_bindings
    op.execute("DROP INDEX IF EXISTS uq_telegram_active_binding")
    op.drop_index(
        "ix_telegram_group_bindings_chat_id",
        table_name="telegram_group_bindings",
    )
    op.drop_index(
        "ix_telegram_group_bindings_department_id",
        table_name="telegram_group_bindings",
    )
    op.drop_table("telegram_group_bindings")
