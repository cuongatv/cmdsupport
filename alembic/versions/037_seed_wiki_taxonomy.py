# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportAttributeAccessIssue=false
"""Seed BIDV KHDN wiki taxonomy knowledge types.

Revision ID: 037
Revises: 036
Create Date: 2026-05-19

Seeds the canonical BIDV KHDN taxonomy rows in ``knowledge_types``. The
migration is idempotent: re-running upgrade leaves any existing rows untouched
and only inserts the missing seeded slugs.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None

knowledge_types = sa.table(
    "knowledge_types",
    sa.column("slug", sa.String),
    sa.column("name", sa.String),
    sa.column("description", sa.Text),
    sa.column("sort_order", sa.Integer),
)

SEED_KNOWLEDGE_TYPES: tuple[tuple[str, str, str], ...] = (
    (
        "business_object.product_service",
        "Sản phẩm & dịch vụ",
        "Nhóm sản phẩm, dịch vụ và gói giải pháp.",
    ),
    (
        "business_object.target_customer",
        "Khách hàng mục tiêu / phân khúc",
        "Phân khúc khách hàng hoặc nhóm mục tiêu.",
    ),
    (
        "business_object.non_credit_development_tool",
        "Công cụ phát triển khách hàng phi tín dụng",
        "Công cụ hỗ trợ phát triển khách hàng phi tín dụng.",
    ),
    (
        "business_object.credit_development_tool",
        "Công cụ phát triển khách hàng tín dụng",
        "Công cụ hỗ trợ phát triển khách hàng tín dụng.",
    ),
    (
        "business_object.campaign_program",
        "Chiến dịch / chương trình thúc đẩy",
        "Chiến dịch, chương trình hoặc đợt thúc đẩy.",
    ),
    (
        "business_object.policy_mechanism",
        "Cơ chế / chính sách",
        "Chính sách, cơ chế và ưu đãi áp dụng.",
    ),
    (
        "business_object.eligibility_condition",
        "Điều kiện / tiêu chí áp dụng",
        "Điều kiện, tiêu chí hoặc ngưỡng áp dụng.",
    ),
    (
        "business_object.process_form",
        "Quy trình / hồ sơ / biểu mẫu",
        "Quy trình, hồ sơ và biểu mẫu nghiệp vụ.",
    ),
    (
        "business_object.risk_compliance",
        "Rủi ro / tuân thủ",
        "Rủi ro, tuân thủ và kiểm soát liên quan.",
    ),
    (
        "business_object.industry_segment",
        "Ngành nghề / lĩnh vực kinh doanh",
        "Ngành nghề hoặc phân khúc lĩnh vực kinh doanh.",
    ),
    (
        "business_object.region_channel",
        "Địa bàn / kênh phân phối",
        "Địa bàn triển khai hoặc kênh phân phối.",
    ),
    (
        "business_object.other",
        "Đối tượng nghiệp vụ khác",
        "Nhóm nghiệp vụ khác chưa phân loại.",
    ),
    (
        "supporting_knowledge.general_context",
        "Bối cảnh / thông tin nền",
        "Thông tin nền, bối cảnh hoặc tổng quan.",
    ),
    (
        "supporting_knowledge.term_explanation",
        "Giải thích thuật ngữ",
        "Giải nghĩa thuật ngữ và khái niệm.",
    ),
    (
        "supporting_knowledge.operational_guidance",
        "Hướng dẫn vận hành / hướng dẫn đọc tài liệu",
        "Hướng dẫn vận hành và cách đọc tài liệu.",
    ),
    (
        "supporting_knowledge.source_background",
        "Thông tin nguồn / xuất xứ tài liệu",
        "Thông tin nguồn, xuất xứ và bối cảnh tài liệu.",
    ),
    (
        "supporting_knowledge.other",
        "Kiến thức bổ trợ khác",
        "Kiến thức bổ trợ còn lại.",
    ),
)


def upgrade() -> None:
    bind = op.get_bind()
    existing_slugs = {
        row.slug
        for row in bind.execute(
            sa.select(knowledge_types.c.slug).where(
                knowledge_types.c.slug.in_([slug for slug, _, _ in SEED_KNOWLEDGE_TYPES])
            )
        )
    }
    rows = [
        {
            "slug": slug,
            "name": name,
            "description": description,
            "sort_order": index,
        }
        for index, (slug, name, description) in enumerate(
            SEED_KNOWLEDGE_TYPES,
            start=1,
        )
        if slug not in existing_slugs
    ]
    if rows:
        op.bulk_insert(knowledge_types, rows)


def downgrade() -> None:
    op.execute(
        sa.delete(knowledge_types).where(
            knowledge_types.c.slug.in_([slug for slug, _, _ in SEED_KNOWLEDGE_TYPES])
        )
    )
