"""Rename default admin email/password from arkon to cmdsupport.

Revision ID: 015
Revises: 014
Create Date: 2026-05-07
"""

import bcrypt
import sqlalchemy as sa

from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def _hash_password(plain: str) -> str:
    """Generate bcrypt hash for a password."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def upgrade() -> None:
    # Idempotent: only updates if the old email exists
    new_hash = _hash_password("cmd@1234")
    op.execute(
        sa.text(
            "UPDATE employees SET email = :new_email, password_hash = :new_hash "
            "WHERE email = :old_email"
        ).bindparams(
            new_email="admin@cmdsupport.com",
            new_hash=new_hash,
            old_email="admin@arkon.local",
        )
    )


def downgrade() -> None:
    old_hash = _hash_password("admin123")
    op.execute(
        sa.text(
            "UPDATE employees SET email = :old_email, password_hash = :old_hash "
            "WHERE email = :new_email"
        ).bindparams(
            old_email="admin@arkon.local",
            old_hash=old_hash,
            new_email="admin@cmdsupport.com",
        )
    )
