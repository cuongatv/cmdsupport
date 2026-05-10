"""CMD Support: provinces, industries, cmd_advisory_sessions tables + seed data.

Revision ID: 016
Revises: 015
Create Date: 2026-05-07
"""

import json
import uuid
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None

DATA_DIR = Path(__file__).resolve().parents[2] / "app" / "data"


def upgrade() -> None:
    # --- provinces ---
    provinces_table = op.create_table(
        "provinces",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(10), unique=True, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("short_name", sa.String(100), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("region", sa.String(10), nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- industries ---
    industries_table = op.create_table(
        "industries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(10), unique=True, nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("level", sa.Integer, nullable=False),
        sa.Column("parent_code", sa.String(10), nullable=True),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("industries_level_idx", "industries", ["level"])
    op.create_index("industries_parent_idx", "industries", ["parent_code"])

    # --- cmd_advisory_sessions ---
    op.create_table(
        "cmd_advisory_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_by_id", UUID(as_uuid=True),
                   sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("customer_name", sa.String(500), nullable=False),
        sa.Column("province_code", sa.String(10), nullable=True),
        sa.Column("province_name", sa.String(200), nullable=True),
        sa.Column("industry_code", sa.String(10), nullable=True),
        sa.Column("industry_name", sa.String(500), nullable=True),
        sa.Column("needs", sa.Text, nullable=False),
        sa.Column("additional_context", sa.Text, nullable=True),
        sa.Column("retrieved_wiki_page_ids", ARRAY(UUID(as_uuid=True)), server_default="{}"),
        sa.Column("retrieved_source_ids", ARRAY(UUID(as_uuid=True)), server_default="{}"),
        sa.Column("result_json", JSONB, nullable=True),
        sa.Column("model_provider", sa.String(50), nullable=True),
        sa.Column("model_id", sa.String(200), nullable=True),
        sa.Column("prompt_version", sa.String(50), nullable=True),
        sa.Column("scope_type", sa.String(20), server_default="global"),
        sa.Column("scope_id", UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(30), server_default="ready"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("cmd_advisory_created_by_idx", "cmd_advisory_sessions", ["created_by_id"])
    op.create_index("cmd_advisory_created_at_idx", "cmd_advisory_sessions", ["created_at"])

    # --- Seed provinces ---
    provinces_path = DATA_DIR / "provinces_vn_2025.json"
    with open(provinces_path, "r", encoding="utf-8") as f:
        provinces_data = json.load(f)

    province_rows = []
    for i, p in enumerate(provinces_data):
        province_rows.append({
            "id": uuid.uuid4(),
            "code": p["code"],
            "name": p["name"],
            "short_name": p["short_name"],
            "type": p["type"],
            "region": p["region"],
            "sort_order": i + 1,
        })
    op.bulk_insert(provinces_table, province_rows)

    # --- Seed industries ---
    industries_path = DATA_DIR / "vsic_2018_level1_2.json"
    with open(industries_path, "r", encoding="utf-8") as f:
        industries_data = json.load(f)

    industry_rows = []
    for i, ind in enumerate(industries_data):
        industry_rows.append({
            "id": uuid.uuid4(),
            "code": ind["code"],
            "name": ind["name"],
            "level": ind["level"],
            "parent_code": ind.get("parent_code"),
            "sort_order": i + 1,
        })
    op.bulk_insert(industries_table, industry_rows)


def downgrade() -> None:
    op.drop_table("cmd_advisory_sessions")
    op.drop_table("industries")
    op.drop_table("provinces")
