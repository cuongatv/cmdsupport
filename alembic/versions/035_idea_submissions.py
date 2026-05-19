"""Public idea submissions for CMD Support feature feedback.

Revision ID: 035
Revises: 034
Create Date: 2026-05-19

Adds two tables to capture community feature ideas submitted from the
public /ideas page:

* ``idea_submissions`` — one row per submission. Captures contributor
  name (required), optional phone/email/department/reference-system,
  the idea description (required), an optional "current pain" and
  "expected benefit" pair, plus a category and admin workflow status.

* ``idea_submission_images`` — N images attached to a submission. The
  binary content lives in MinIO under
  ``idea_submissions/<submission_id>/<uuid>.<ext>`` — only the storage
  key + mime + size are stored here.

Submissions are public, so no foreign key to ``employees``. Admins
manage them through ``/admin/ideas``.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "idea_submissions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("contributor_name", sa.String(200), nullable=False),
        sa.Column("contributor_phone", sa.String(50), nullable=True),
        sa.Column("contributor_email", sa.String(200), nullable=True),
        sa.Column("contributor_department", sa.String(200), nullable=True),
        sa.Column("title", sa.String(300), nullable=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("current_pain", sa.Text, nullable=True),
        sa.Column("expected_benefit", sa.Text, nullable=True),
        sa.Column("reference_system", sa.String(500), nullable=True),
        sa.Column(
            "category",
            sa.String(30),
            nullable=False,
            server_default="feature",
            comment="feature|improvement|bug|ux|other",
        ),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="new",
            comment="new|reviewing|planned|in_progress|shipped|declined",
        ),
        sa.Column("admin_notes", sa.Text, nullable=True),
        sa.Column("submitter_ip", sa.String(64), nullable=True),
        sa.Column("submitter_user_agent", sa.String(500), nullable=True),
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
            "category IN ('feature', 'improvement', 'bug', 'ux', 'other')",
            name="ck_idea_submissions_category",
        ),
        sa.CheckConstraint(
            "status IN ('new', 'reviewing', 'planned', 'in_progress', 'shipped', 'declined')",
            name="ck_idea_submissions_status",
        ),
    )
    op.create_index(
        "ix_idea_submissions_created_at",
        "idea_submissions",
        ["created_at"],
    )
    op.create_index(
        "ix_idea_submissions_status",
        "idea_submissions",
        ["status"],
    )

    op.create_table(
        "idea_submission_images",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "submission_id",
            UUID(as_uuid=True),
            sa.ForeignKey("idea_submissions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("file_name", sa.String(300), nullable=True),
        sa.Column("content_type", sa.String(100), nullable=True),
        sa.Column("size_bytes", sa.Integer, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_idea_submission_images_submission_id",
        "idea_submission_images",
        ["submission_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_idea_submission_images_submission_id",
        table_name="idea_submission_images",
    )
    op.drop_table("idea_submission_images")
    op.drop_index("ix_idea_submissions_status", table_name="idea_submissions")
    op.drop_index("ix_idea_submissions_created_at", table_name="idea_submissions")
    op.drop_table("idea_submissions")
