# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportImplicitStringConcatenation=false
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ConsultingRuleProduct, KnowledgeType, Source, WikiPage
from tests.fixtures.wiki_taxonomy import (
    FIXTURE_NAMESPACE,
    create_rule_linked_page,
    create_sentinel_employee,
    create_source_with_knowledge_type,
    create_taxonomy_pages,
)

pytestmark = pytest.mark.asyncio


async def test_create_taxonomy_pages_deterministic(db_session: AsyncSession):
    pages = await create_taxonomy_pages(db_session)

    assert set(pages) == {
        "sme-working-capital-loan",
        "khdn-loan-condition",
        "khdn-credit-development",
        "bidv-sme-product-catalog-source",
    }

    expected = {
        "sme-working-capital-loan": (
            "entity",
            "# Working capital loan\n\n"
            "Gói tín dụng SME dành cho doanh nghiệp nhỏ và vừa cần vốn quay vòng.\n\n"
            "Working capital loan helps SMEs manage cash flow and short-term funding.\n",
            ["business_object.product_service"],
            uuid.uuid5(FIXTURE_NAMESPACE, "wiki-page::sme-working-capital-loan"),
        ),
        "khdn-loan-condition": (
            "concept",
            "# Loan condition overview\n\n"
            "Gói tín dụng SME có các điều kiện áp dụng rõ ràng cho khách hàng doanh nghiệp.\n\n"
            "Working capital loan eligibility depends on revenue, profile, and exposure.\n",
            ["business_object.eligibility_condition"],
            uuid.uuid5(FIXTURE_NAMESPACE, "wiki-page::khdn-loan-condition"),
        ),
        "khdn-credit-development": (
            "topic",
            "# Credit development topic\n\n"
            "Gói tín dụng SME là một chủ đề phát triển tín dụng quan trọng.\n\n"
            "Working capital loan expansion should stay aligned with policy and risk.\n",
            ["business_object.credit_development_tool"],
            uuid.uuid5(FIXTURE_NAMESPACE, "wiki-page::khdn-credit-development"),
        ),
        "bidv-sme-product-catalog-source": (
            "source",
            "# Source catalog note\n\n"
            "Gói tín dụng SME được mô tả trong tài liệu gốc này.\n\n"
            "Working capital loan appears in the source corpus for taxonomy fixtures.\n",
            ["supporting_knowledge.source_background"],
            uuid.uuid5(FIXTURE_NAMESPACE, "wiki-page::bidv-sme-product-catalog-source"),
        ),
    }

    for slug, page in pages.items():
        page_type, body, knowledge_type_slugs, expected_id = expected[slug]
        assert page.slug == slug
        assert page.id == expected_id
        assert page.page_type == page_type
        assert page.content_md == body
        assert page.knowledge_type_slugs == knowledge_type_slugs
        assert "Working capital loan" in page.content_md
        assert "Gói tín dụng SME" in page.content_md

        persisted = (
            await db_session.execute(select(WikiPage).where(WikiPage.id == page.id))
        ).scalar_one()
        assert persisted.slug == slug
        assert persisted.content_md == body
        assert persisted.knowledge_type_slugs == knowledge_type_slugs
        assert persisted.taxonomy_classifier_version == "v1"


async def test_create_rule_linked_page_and_source_fixture(db_session: AsyncSession):
    employee = await create_sentinel_employee(db_session)
    page, rule = await create_rule_linked_page(db_session, employee.id)

    assert page.slug == "sme-working-capital-loan-rule-linked"
    assert page.id == uuid.uuid5(
        FIXTURE_NAMESPACE, "wiki-page::sme-working-capital-loan-rule-linked"
    )
    assert "Working capital loan" in page.content_md
    assert "Gói tín dụng SME" in page.content_md
    assert rule.wiki_page_id == page.id
    assert rule.id == uuid.uuid5(
        FIXTURE_NAMESPACE,
        "consulting-rule-product::sme-working-capital-loan-rule-linked",
    )
    assert rule.customer_persona == "SME relationship manager"

    linked_count = (
        await db_session.execute(
            select(func.count()).select_from(ConsultingRuleProduct).where(
                ConsultingRuleProduct.wiki_page_id == page.id
            )
        )
    ).scalar_one()
    assert linked_count == 1

    knowledge_type = (
        await db_session.execute(
            select(KnowledgeType).where(
                KnowledgeType.slug == "business_object.product_service"
            )
        )
    ).scalar_one()
    source = await create_source_with_knowledge_type(db_session, knowledge_type.id)

    assert source.id == uuid.uuid5(
        FIXTURE_NAMESPACE, f"source::{knowledge_type.id}"
    )
    assert source.knowledge_type_id == knowledge_type.id
    assert "Working capital loan" in source.full_text
    assert "Gói tín dụng SME" in source.full_text

    persisted_source = (
        await db_session.execute(select(Source).where(Source.id == source.id))
    ).scalar_one()
    assert persisted_source.knowledge_type_id == knowledge_type.id
    assert persisted_source.full_text == source.full_text
