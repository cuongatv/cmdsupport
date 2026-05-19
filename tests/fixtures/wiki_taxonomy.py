# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportDuplicateImport=false, reportDeprecated=false, reportImplicitStringConcatenation=false, reportUnknownLambdaType=false, reportUnknownArgumentType=false
"""Reusable wiki taxonomy fixtures for reclassification tests."""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Iterator
from unittest.mock import patch

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    ConsultingRuleProduct,
    Department,
    Employee,
    Source,
    WikiPage,
)
from app.services import consulting_rule_service, wiki_service

__all__ = [
    "FIXTURE_NAMESPACE",
    "create_bulk_taxonomy_pages",
    "create_rule_linked_page",
    "create_sentinel_employee",
    "create_source_with_knowledge_type",
    "create_taxonomy_pages",
]

FIXTURE_NAMESPACE = uuid.UUID("7e61d8c5-7c44-4f2e-b8b5-1f2d4f7b3a11")
RULE_LINKED_PAGE_SLUG = "sme-working-capital-loan-rule-linked"

TAXONOMY_PAGE_BODIES = {
    "sme-working-capital-loan": (
        "# Working capital loan\n\n"
        "Gói tín dụng SME dành cho doanh nghiệp nhỏ và vừa cần vốn quay vòng.\n\n"
        "Working capital loan helps SMEs manage cash flow and short-term funding.\n"
    ),
    "khdn-loan-condition": (
        "# Loan condition overview\n\n"
        "Gói tín dụng SME có các điều kiện áp dụng rõ ràng cho khách hàng doanh nghiệp.\n\n"
        "Working capital loan eligibility depends on revenue, profile, and exposure.\n"
    ),
    "khdn-credit-development": (
        "# Credit development topic\n\n"
        "Gói tín dụng SME là một chủ đề phát triển tín dụng quan trọng.\n\n"
        "Working capital loan expansion should stay aligned with policy and risk.\n"
    ),
    "bidv-sme-product-catalog-source": (
        "# Source catalog note\n\n"
        "Gói tín dụng SME được mô tả trong tài liệu gốc này.\n\n"
        "Working capital loan appears in the source corpus for taxonomy fixtures.\n"
    ),
    RULE_LINKED_PAGE_SLUG: (
        "# Working capital loan\n\n"
        "Gói tín dụng SME dành cho doanh nghiệp nhỏ và vừa cần vốn quay vòng.\n\n"
        "Working capital loan stays linked to a consulting rule fixture.\n"
    ),
}

TAXONOMY_PAGE_TYPES = {
    "sme-working-capital-loan": "entity",
    "khdn-loan-condition": "concept",
    "khdn-credit-development": "topic",
    "bidv-sme-product-catalog-source": "source",
    RULE_LINKED_PAGE_SLUG: "entity",
}

TAXONOMY_PAGE_KT_SLUGS = {
    "sme-working-capital-loan": ["business_object.product_service"],
    "khdn-loan-condition": ["business_object.eligibility_condition"],
    "khdn-credit-development": ["business_object.credit_development_tool"],
    "bidv-sme-product-catalog-source": ["supporting_knowledge.source_background"],
    RULE_LINKED_PAGE_SLUG: ["business_object.product_service"],
}

SOURCE_FULL_TEXT = (
    "# BIDV SME product catalog source\n\n"
    "Gói tín dụng SME is documented here for source-level taxonomy fixtures.\n\n"
    "Working capital loan is preserved verbatim for no-translation assertions.\n"
)


@contextmanager
def _patched_model_uuid4(*values: uuid.UUID) -> Iterator[None]:
    with patch("app.database.models.uuid.uuid4", side_effect=list(values)):
        yield


def _stable_uuid(*parts: str) -> uuid.UUID:
    return uuid.uuid5(FIXTURE_NAMESPACE, "::".join(parts))


async def _rekey_wiki_page(
    session: AsyncSession,
    *,
    old_page_id: uuid.UUID,
    new_page_id: uuid.UUID,
    slug: str,
) -> WikiPage:
    await session.execute(
        text("UPDATE wiki_pages SET id = :new_id WHERE id = :old_id"),
        {"new_id": new_page_id, "old_id": old_page_id},
    )
    await session.execute(
        text("UPDATE wiki_page_revisions SET page_id = :new_id WHERE page_id = :old_id"),
        {"new_id": new_page_id, "old_id": old_page_id},
    )
    await session.run_sync(lambda sync_session: sync_session.expunge_all())
    result = await session.execute(select(WikiPage).where(WikiPage.slug == slug))
    return result.scalar_one()


async def _create_wiki_page(
    session: AsyncSession,
    slug: str,
    *,
    page_type: str,
    content_md: str,
    summary: str,
    knowledge_type_slugs: list[str],
    taxonomy_confidence: float | None = None,
    taxonomy_rationale: str | None = None,
    taxonomy_needs_review: bool | None = None,
    taxonomy_classifier_version: str | None = None,
) -> WikiPage:
    page_id = _stable_uuid("wiki-page", slug)
    revision_id = _stable_uuid("wiki-page-revision", slug)
    with _patched_model_uuid4(page_id, revision_id):
        page = await wiki_service.apply_create(
            session,
            slug=slug,
            title=slug.replace("-", " ").title(),
            page_type=page_type,
            content_md=content_md,
            summary=summary,
            knowledge_type_slugs=knowledge_type_slugs,
            source_ids=[],
            taxonomy_confidence=taxonomy_confidence,
            taxonomy_rationale=taxonomy_rationale,
            taxonomy_needs_review=taxonomy_needs_review,
            taxonomy_classifier_version=taxonomy_classifier_version,
        )
    return await _rekey_wiki_page(
        session,
        old_page_id=page.id,
        new_page_id=page_id,
        slug=slug,
    )


async def create_taxonomy_pages(session: AsyncSession) -> dict[str, WikiPage]:
    pages: dict[str, WikiPage] = {}
    pages["sme-working-capital-loan"] = await _create_wiki_page(
        session,
        "sme-working-capital-loan",
        page_type=TAXONOMY_PAGE_TYPES["sme-working-capital-loan"],
        content_md=TAXONOMY_PAGE_BODIES["sme-working-capital-loan"],
        summary="Fixture page for sme-working-capital-loan.",
        knowledge_type_slugs=TAXONOMY_PAGE_KT_SLUGS["sme-working-capital-loan"],
        taxonomy_confidence=0.94,
        taxonomy_rationale="Strong product-page signal from SME lending terminology.",
        taxonomy_needs_review=False,
        taxonomy_classifier_version="v1",
    )
    pages["khdn-loan-condition"] = await _create_wiki_page(
        session,
        "khdn-loan-condition",
        page_type=TAXONOMY_PAGE_TYPES["khdn-loan-condition"],
        content_md=TAXONOMY_PAGE_BODIES["khdn-loan-condition"],
        summary="Fixture page for khdn-loan-condition.",
        knowledge_type_slugs=TAXONOMY_PAGE_KT_SLUGS["khdn-loan-condition"],
        taxonomy_confidence=0.71,
        taxonomy_rationale="Eligibility content indicates a concept page about conditions.",
        taxonomy_needs_review=True,
        taxonomy_classifier_version="v1",
    )
    pages["khdn-credit-development"] = await _create_wiki_page(
        session,
        "khdn-credit-development",
        page_type=TAXONOMY_PAGE_TYPES["khdn-credit-development"],
        content_md=TAXONOMY_PAGE_BODIES["khdn-credit-development"],
        summary="Fixture page for khdn-credit-development.",
        knowledge_type_slugs=TAXONOMY_PAGE_KT_SLUGS["khdn-credit-development"],
        taxonomy_confidence=0.83,
        taxonomy_rationale="Topic-level coverage for credit development workflow.",
        taxonomy_needs_review=False,
        taxonomy_classifier_version="v1",
    )
    pages["bidv-sme-product-catalog-source"] = await _create_wiki_page(
        session,
        "bidv-sme-product-catalog-source",
        page_type=TAXONOMY_PAGE_TYPES["bidv-sme-product-catalog-source"],
        content_md=TAXONOMY_PAGE_BODIES["bidv-sme-product-catalog-source"],
        summary="Fixture page for bidv-sme-product-catalog-source.",
        knowledge_type_slugs=TAXONOMY_PAGE_KT_SLUGS["bidv-sme-product-catalog-source"],
        taxonomy_confidence=0.88,
        taxonomy_rationale="Source-level page carrying source background taxonomy.",
        taxonomy_needs_review=False,
        taxonomy_classifier_version="v1",
    )
    return pages


async def create_bulk_taxonomy_pages(
    session: AsyncSession,
    count: int,
    slug_prefix: str,
) -> list[WikiPage]:
    pages: list[WikiPage] = []
    slug_cycle = [
        ["business_object.product_service"],
        ["business_object.eligibility_condition"],
        ["business_object.policy_mechanism"],
        ["supporting_knowledge.source_background"],
    ]
    type_cycle = ["entity", "concept", "topic", "source"]
    for index in range(count):
        slug = f"{slug_prefix}-{index:03d}"
        pages.append(
            await _create_wiki_page(
                session,
                slug,
                page_type=type_cycle[index % len(type_cycle)],
                content_md=(
                    f"# Bulk taxonomy page {index:03d}\n\n"
                    "Gói tín dụng SME deterministic bulk fixture for preview pagination.\n"
                ),
                summary=f"Bulk taxonomy fixture {index:03d}.",
                knowledge_type_slugs=list(slug_cycle[index % len(slug_cycle)]),
                taxonomy_confidence=0.80 + ((index % 10) / 100),
                taxonomy_rationale=f"Bulk fixture rationale {index:03d}.",
                taxonomy_needs_review=False,
                taxonomy_classifier_version="v1",
            )
        )
    return pages


async def create_sentinel_employee(session: AsyncSession) -> Employee:
    department_id = _stable_uuid("department", "taxonomy-fixture")
    employee_id = _stable_uuid("employee", "taxonomy-fixture")
    department = Department(
        id=department_id,
        name="Taxonomy Fixture Department",
        description="Sentinel department for wiki taxonomy fixtures.",
    )
    employee = Employee(
        id=employee_id,
        name="Taxonomy Fixture Employee",
        email="taxonomy.fixture@example.com",
        username="taxonomy.fixture",
        role="employee",
        department_id=department_id,
    )
    session.add_all([department, employee])
    await session.flush()
    await session.refresh(employee)
    return employee


async def _rekey_rule(
    session: AsyncSession,
    *,
    old_rule_id: uuid.UUID,
    new_rule_id: uuid.UUID,
) -> ConsultingRuleProduct:
    await session.execute(
        text("UPDATE consulting_rules_product SET id = :new_id WHERE id = :old_id"),
        {"new_id": new_rule_id, "old_id": old_rule_id},
    )
    await session.run_sync(lambda sync_session: sync_session.expunge_all())
    result = await session.execute(
        select(ConsultingRuleProduct).where(ConsultingRuleProduct.id == new_rule_id)
    )
    return result.scalar_one()


async def create_rule_linked_page(
    session: AsyncSession,
    employee_id: uuid.UUID,
) -> tuple[WikiPage, ConsultingRuleProduct]:
    page = await _create_wiki_page(
        session,
        RULE_LINKED_PAGE_SLUG,
        page_type=TAXONOMY_PAGE_TYPES[RULE_LINKED_PAGE_SLUG],
        content_md=TAXONOMY_PAGE_BODIES[RULE_LINKED_PAGE_SLUG],
        summary="Fixture page linked to a consulting rule.",
        knowledge_type_slugs=TAXONOMY_PAGE_KT_SLUGS[RULE_LINKED_PAGE_SLUG],
        taxonomy_confidence=0.94,
        taxonomy_rationale="Strong product-page signal from SME lending terminology.",
        taxonomy_needs_review=False,
        taxonomy_classifier_version="v1",
    )
    rule_id = _stable_uuid("consulting-rule-product", page.slug)
    with _patched_model_uuid4(rule_id):
        user = await session.get(Employee, employee_id)
        if user is None:
            raise ValueError(f"Missing sentinel employee: {employee_id}")
        rule = await consulting_rule_service.upsert_product_rule(
            session,
            user,
            wiki_page_id=page.id,
            product_name_custom=None,
            basic_info="Fixture product rule linked to wiki page.",
            customer_persona="SME relationship manager",
        )
    rule = await _rekey_rule(session, old_rule_id=rule.id, new_rule_id=rule_id)
    return page, rule


async def create_source_with_knowledge_type(
    session: AsyncSession,
    knowledge_type_id: uuid.UUID,
) -> Source:
    source = Source(
        id=_stable_uuid("source", str(knowledge_type_id)),
        title="BIDV SME product catalog source",
        full_text=SOURCE_FULL_TEXT,
        source_type="file",
        knowledge_type_id=knowledge_type_id,
        status="done",
        progress=100,
        file_name="bidv-sme-product-catalog.md",
    )
    session.add(source)
    await session.flush()
    await session.refresh(source)
    return source
