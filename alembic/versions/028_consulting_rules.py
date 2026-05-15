"""Add consulting rules tables (product / segment / province).

Revision ID: 028
Revises: 027
Create Date: 2026-05-15
"""

import sqlalchemy as sa

from alembic import op

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------ product
    op.create_table(
        "consulting_rules_product",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "wiki_page_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("wiki_pages.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("product_name_custom", sa.String(length=300), nullable=True),
        sa.Column("basic_info", sa.Text(), nullable=True),
        sa.Column(
            "customer_persona",
            sa.Text(),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column(
            "created_by_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_by_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
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
            "(wiki_page_id IS NOT NULL)::int + (product_name_custom IS NOT NULL)::int = 1",
            name="ck_consulting_rule_product_xor",
        ),
    )
    op.create_index(
        "ux_consulting_rule_product_wiki",
        "consulting_rules_product",
        ["wiki_page_id"],
        unique=True,
        postgresql_where=sa.text("wiki_page_id IS NOT NULL"),
    )
    op.create_index(
        "ux_consulting_rule_product_custom",
        "consulting_rules_product",
        ["product_name_custom"],
        unique=True,
        postgresql_where=sa.text("product_name_custom IS NOT NULL"),
    )

    # ------------------------------------------------------------------ segment
    op.create_table(
        "consulting_rules_segment",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("segment", sa.String(length=30), nullable=False, unique=True),
        sa.Column("basic_info", sa.Text(), nullable=True),
        sa.Column(
            "segment_specifics",
            sa.Text(),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column(
            "created_by_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_by_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
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

    # ----------------------------------------------------------------- province
    op.create_table(
        "consulting_rules_province",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "province_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("provinces.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("basic_info", sa.Text(), nullable=True),
        sa.Column(
            "province_specifics",
            sa.Text(),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column(
            "created_by_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_by_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
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
    op.drop_table("consulting_rules_province")
    op.drop_table("consulting_rules_segment")
    op.drop_index(
        "ux_consulting_rule_product_custom",
        table_name="consulting_rules_product",
    )
    op.drop_index(
        "ux_consulting_rule_product_wiki",
        table_name="consulting_rules_product",
    )
    op.drop_table("consulting_rules_product")
