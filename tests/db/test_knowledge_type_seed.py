# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportDuplicateImport=false
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import engine
from app.database.models import KnowledgeType

pytestmark = pytest.mark.asyncio

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CMD = [sys.executable, '-m', 'alembic']
SENTINEL_SLUG = 'test.sentinel.knowledge_type'

EXPECTED_TAXONOMY = {
    'business_object.product_service': 'Sản phẩm & dịch vụ',
    'business_object.target_customer': 'Khách hàng mục tiêu / phân khúc',
    'business_object.non_credit_development_tool': 'Công cụ phát triển khách hàng phi tín dụng',
    'business_object.credit_development_tool': 'Công cụ phát triển khách hàng tín dụng',
    'business_object.campaign_program': 'Chiến dịch / chương trình thúc đẩy',
    'business_object.policy_mechanism': 'Cơ chế / chính sách',
    'business_object.eligibility_condition': 'Điều kiện / tiêu chí áp dụng',
    'business_object.process_form': 'Quy trình / hồ sơ / biểu mẫu',
    'business_object.risk_compliance': 'Rủi ro / tuân thủ',
    'business_object.industry_segment': 'Ngành nghề / lĩnh vực kinh doanh',
    'business_object.region_channel': 'Địa bàn / kênh phân phối',
    'business_object.other': 'Đối tượng nghiệp vụ khác',
    'supporting_knowledge.general_context': 'Bối cảnh / thông tin nền',
    'supporting_knowledge.term_explanation': 'Giải thích thuật ngữ',
    'supporting_knowledge.operational_guidance': 'Hướng dẫn vận hành / hướng dẫn đọc tài liệu',
    'supporting_knowledge.source_background': 'Thông tin nguồn / xuất xứ tài liệu',
    'supporting_knowledge.other': 'Kiến thức bổ trợ khác',
}


async def _run_alembic(*args: str) -> subprocess.CompletedProcess[str]:
    return await asyncio.to_thread(
        subprocess.run,
        [*ALEMBIC_CMD, *args],
        cwd=REPO_ROOT,
        env={**os.environ},
        text=True,
        capture_output=True,
        check=True,
    )


async def _cleanup_sentinel() -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text('DELETE FROM knowledge_types WHERE slug = :slug'),
            {'slug': SENTINEL_SLUG},
        )


async def _seed_sentinel() -> None:
    await _cleanup_sentinel()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                '''
                INSERT INTO knowledge_types (id, slug, name, description, sort_order)
                VALUES (:id, :slug, :name, :description, :sort_order)
                '''
            ),
            {
                'id': uuid.uuid4(),
                'slug': SENTINEL_SLUG,
                'name': 'Sentinel Knowledge Type',
                'description': 'Seed row for migration roundtrip verification.',
                'sort_order': 9999,
            },
        )


async def _fetch_taxonomy_rows() -> dict[str, tuple[str, str | None]]:
    table = KnowledgeType.__table__
    async with engine.connect() as conn:
        result = await conn.execute(
            select(
                table.c.slug,
                table.c.name,
                table.c.description,
            ).where(table.c.slug.in_(list(EXPECTED_TAXONOMY) + [SENTINEL_SLUG]))
        )
        return {
            row.slug: (row.name, row.description)
            for row in result.fetchall()
        }


async def test_knowledge_type_seed_roundtrip(db_session: AsyncSession):
    await db_session.execute(text('SELECT 1'))
    await _seed_sentinel()

    upgrade_1 = await _run_alembic('upgrade', 'head')
    rows_after_upgrade = await _fetch_taxonomy_rows()

    assert rows_after_upgrade[SENTINEL_SLUG][0] == 'Sentinel Knowledge Type'
    assert rows_after_upgrade[SENTINEL_SLUG][1] == 'Seed row for migration roundtrip verification.'
    assert set(EXPECTED_TAXONOMY).issubset(rows_after_upgrade)
    for slug, expected_name in EXPECTED_TAXONOMY.items():
        assert rows_after_upgrade[slug][0] == expected_name
        assert rows_after_upgrade[slug][1]

    try:
        downgrade = await _run_alembic('downgrade', '036')
        rows_after_downgrade = await _fetch_taxonomy_rows()

        assert rows_after_downgrade[SENTINEL_SLUG][0] == 'Sentinel Knowledge Type'
        assert rows_after_downgrade[SENTINEL_SLUG][1] == 'Seed row for migration roundtrip verification.'
        assert set(EXPECTED_TAXONOMY).isdisjoint(rows_after_downgrade)
    finally:
        upgrade_2 = await _run_alembic('upgrade', 'head')

    rows_after_second_upgrade = await _fetch_taxonomy_rows()

    assert rows_after_second_upgrade[SENTINEL_SLUG][0] == 'Sentinel Knowledge Type'
    assert rows_after_second_upgrade[SENTINEL_SLUG][1] == 'Seed row for migration roundtrip verification.'
    assert set(EXPECTED_TAXONOMY).issubset(rows_after_second_upgrade)
    for slug, expected_name in EXPECTED_TAXONOMY.items():
        assert rows_after_second_upgrade[slug][0] == expected_name
        assert rows_after_second_upgrade[slug][1]

    assert upgrade_1.returncode == 0
    assert downgrade.returncode == 0
    assert upgrade_2.returncode == 0

    await _cleanup_sentinel()
