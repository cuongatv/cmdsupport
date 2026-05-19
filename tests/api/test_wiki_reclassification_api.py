"""
API-level tests for the wiki taxonomy reclassification routes (T11).

These tests are in-process via httpx ASGITransport. They never touch
PostgreSQL: ``get_db`` is replaced with a no-op session stub, and the T9 /
T10 service functions are monkeypatched at the *router module* import path
(``app.routers.wiki_reclassify.preview_reclassification`` /
``apply_reclassification``) so we exercise only the HTTP wiring and RBAC
gate — not classifier internals.

Two cases:

* ``test_preview_api_returns_diff_contract`` — admin token, mocked T9
  preview, asserts 200 + diff envelope on each page.
* ``test_apply_api_rejects_unauthorized_user`` — no token, asserts 401 and
  proves the apply service was never invoked (DB taxonomy stays untouched
  because the patched apply function would have flipped a sentinel).
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Stub session + dependency overrides
# ---------------------------------------------------------------------------


class _StubSession:
    """Minimal AsyncSession-ish stub. The service is mocked, so we only need
    ``commit`` to be awaitable for the apply route's post-write audit flush.
    """

    async def commit(self) -> None:
        return None

    async def execute(self, *_args, **_kwargs):
        class _Scalars:
            def all(self):
                return []

            def scalar(self):
                return 0

        class _Result:
            def scalars(self):
                return _Scalars()

            def scalar(self):
                return 0

            def all(self):
                return []

        return _Result()


_ADMIN_ID = uuid.uuid4()
_ADMIN = SimpleNamespace(
    id=_ADMIN_ID,
    name="Reclassify Admin",
    email="admin@cmdsupport.local",
    role="admin",
    custom_role=None,
    department_id=uuid.uuid4(),
    is_active=True,
)


@pytest_asyncio.fixture
async def client_with_admin() -> AsyncIterator[httpx.AsyncClient]:
    """ASGI client with ``get_db`` stubbed and ``get_current_user`` forced to
    an admin. ``require_permission`` short-circuits for admins, so the route
    body executes."""
    from app.database import get_db
    from app.main import app
    from app.services.auth_service import get_current_user

    async def _stub_db():
        yield _StubSession()

    async def _admin_user():
        return _ADMIN

    app.dependency_overrides[get_db] = _stub_db
    app.dependency_overrides[get_current_user] = _admin_user
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as ac:
        try:
            yield ac
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def client_no_auth() -> AsyncIterator[httpx.AsyncClient]:
    """ASGI client with ``get_db`` stubbed but no auth override — hits the
    real ``get_current_user`` which raises 401 when no bearer token is
    present.
    """
    from app.database import get_db
    from app.main import app

    async def _stub_db():
        yield _StubSession()

    app.dependency_overrides[get_db] = _stub_db
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as ac:
        try:
            yield ac
        finally:
            app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# test_preview_api_returns_diff_contract
# ---------------------------------------------------------------------------


async def test_preview_api_returns_diff_contract(
    client_with_admin: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    """POST /api/wiki/reclassify/preview with admin token returns the T9
    preview envelope verbatim. Asserts the per-page diff contract.
    """
    import app.routers.wiki_reclassify as router_module

    source_id = uuid.uuid4()
    wiki_page_id = uuid.uuid4()

    canned_preview = {
        "preview_id": "preview-fixture-123",
        "page_count": 1,
        "flagged_count": 1,
        "pages": [
            {
                "wiki_page_id": str(wiki_page_id),
                "slug": "products/loans/working-capital",
                "title": "Working Capital Loan",
                "page_type": "product",
                "old_slugs": ["business_object.other"],
                "new_slugs": ["business_object.loan_product"],
                "confidence": 0.84,
                "rationale": "Title and summary clearly describe a loan product.",
                "needs_review": False,
                "classifier_version": "test-vfixture",
                "rule_link_count": 3,
                "impact_flags": ["rule_linked_tier_change"],
            }
        ],
    }

    calls: list[dict] = []

    async def _stub_preview(_session, **kwargs):
        calls.append(kwargs)
        return canned_preview

    monkeypatch.setattr(router_module, "preview_reclassification", _stub_preview)

    resp = await client_with_admin.post(
        "/api/wiki/reclassify/preview",
        json={"source_id": str(source_id), "scope_type": "global"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Envelope
    assert body["preview_id"] == "preview-fixture-123"
    assert body["page_count"] == 1
    assert body["flagged_count"] == 1
    assert isinstance(body["pages"], list) and len(body["pages"]) == 1

    # Per-page diff contract
    page = body["pages"][0]
    assert page["old_slugs"] == ["business_object.other"]
    assert page["new_slugs"] == ["business_object.loan_product"]
    assert page["rule_link_count"] == 3
    assert page["needs_review"] is False
    assert "rule_linked_tier_change" in page["impact_flags"]

    # Service was called with the expected filter kwargs (UUIDs coerced)
    assert len(calls) == 1
    assert calls[0]["source_id"] == source_id
    assert calls[0]["scope_type"] == "global"


# ---------------------------------------------------------------------------
# test_apply_api_rejects_unauthorized_user
# ---------------------------------------------------------------------------


async def test_apply_api_rejects_unauthorized_user(
    client_no_auth: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    """POST /api/wiki/reclassify/apply without auth returns 401 AND the
    service is never invoked, proving the DB taxonomy is untouched.

    The sentinel pattern: we install a spy stub on
    ``apply_reclassification`` that records every call. If RBAC truly blocked
    the request, the list stays empty.
    """
    import app.routers.wiki_reclassify as router_module

    invoked: list[dict] = []

    async def _spy_apply(_session, **kwargs):
        invoked.append(kwargs)
        return {
            "preview_id": "should-not-happen",
            "applied_count": 999,
            "skipped_count": 0,
            "flagged_count": 0,
            "unchanged_count": 0,
            "applied_page_ids": [],
            "skipped_reasons": {},
        }

    monkeypatch.setattr(router_module, "apply_reclassification", _spy_apply)

    resp = await client_no_auth.post(
        "/api/wiki/reclassify/apply",
        json={
            "preview": {
                "preview_id": "p-1",
                "page_count": 0,
                "flagged_count": 0,
                "pages": [],
            },
            "force_rule_linked_tier_change": False,
        },
    )

    # 401 (no token) — RBAC permission check would yield 403 if a non-admin
    # token were present, so we accept either as "blocked".
    assert resp.status_code in (401, 403), resp.text

    # Hard proof the apply service was never reached → DB taxonomy unchanged.
    assert invoked == []
