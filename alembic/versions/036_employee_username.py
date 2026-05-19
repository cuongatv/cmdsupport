"""Add username column to employees + backfill from email.

Revision ID: 036
Revises: 035
Create Date: 2026-05-19

Adds a dedicated ``username`` login handle to the employees table so users
can sign in with a username instead of an email. Email stays mandatory and
remains a login alias (auth resolves either to the same row).

Backfill strategy for the existing rows:
  * Take the local-part of the email (text before ``@``).
  * Normalise to ``[a-z0-9._-]`` and lowercase.
  * If two rows would collide after normalisation, suffix with the first 8
    characters of the row's UUID.

The column is added nullable, backfilled in a single ``op.execute`` block,
then altered to NOT NULL and given a unique index.
"""

import sqlalchemy as sa

from alembic import op

revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "employees",
        sa.Column("username", sa.String(100), nullable=True),
    )

    # Backfill: lowercase email local-part, replace non-[a-z0-9._-] with '_',
    # collapse repeats, suffix uuid8 on collision.
    op.execute(
        r"""
        UPDATE employees AS e
        SET username = sub.candidate
        FROM (
            SELECT
                id,
                CASE
                    WHEN base_count > 1 THEN base || '_' || substr(id::text, 1, 8)
                    ELSE base
                END AS candidate
            FROM (
                SELECT
                    id,
                    base,
                    COUNT(*) OVER (PARTITION BY base) AS base_count
                FROM (
                    SELECT
                        id,
                        regexp_replace(
                            lower(split_part(email, '@', 1)),
                            '[^a-z0-9._-]+',
                            '_',
                            'g'
                        ) AS base
                    FROM employees
                ) normalised
            ) counted
        ) AS sub
        WHERE e.id = sub.id
        """
    )

    # Any rows where the local-part normalised to an empty string fall back to
    # `user_<uuid8>` so the NOT NULL + UNIQUE constraints don't trip.
    op.execute(
        r"""
        UPDATE employees
        SET username = 'user_' || substr(id::text, 1, 8)
        WHERE username IS NULL OR username = ''
        """
    )

    op.alter_column("employees", "username", nullable=False)
    op.create_unique_constraint(
        "uq_employees_username",
        "employees",
        ["username"],
    )
    op.create_index(
        "ix_employees_username",
        "employees",
        ["username"],
    )


def downgrade() -> None:
    op.drop_index("ix_employees_username", table_name="employees")
    op.drop_constraint(
        "uq_employees_username", "employees", type_="unique"
    )
    op.drop_column("employees", "username")
