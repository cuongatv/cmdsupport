"""CMD Advisory v2: partial UNIQUE on input_fingerprint for ready rows.

Closes the reuse-check + insert race: two concurrent identical requests would
both miss the cache and insert duplicate sessions. Postgres partial unique
index serializes the second insert; service catches IntegrityError and reuses
the winner.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-12
"""

from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the non-unique index from migration 019; the partial unique index
    # below covers the same lookup pattern (WHERE input_fingerprint = ?).
    op.drop_index(
        "cmd_advisory_fingerprint_idx",
        table_name="cmd_advisory_sessions",
    )
    op.create_index(
        "cmd_advisory_fingerprint_ready_uniq_idx",
        "cmd_advisory_sessions",
        ["input_fingerprint"],
        unique=True,
        postgresql_where="status = 'ready' AND input_fingerprint IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index(
        "cmd_advisory_fingerprint_ready_uniq_idx",
        table_name="cmd_advisory_sessions",
    )
    op.create_index(
        "cmd_advisory_fingerprint_idx",
        "cmd_advisory_sessions",
        ["input_fingerprint"],
    )
