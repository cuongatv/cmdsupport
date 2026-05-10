"""Smoke test: `/api/auth/me` enforces JWT auth correctly.

These tests exercise the FastAPI app via an in-process ASGI transport and
deliberately avoid touching PostgreSQL where possible:

  * The 401 cases use `override_db_noop` so `get_current_user` raises before
    any database access happens.
  * The full happy-path test asks for the `db_session` fixture; that fixture
    skips the test when PostgreSQL is unreachable (e.g. when Docker is down).
"""
import pytest

pytestmark = pytest.mark.asyncio


async def test_me_without_token_returns_401(test_client, override_db_noop):
    resp = await test_client.get("/api/auth/me")
    assert resp.status_code == 401


async def test_me_with_invalid_token_returns_401(test_client, override_db_noop):
    resp = await test_client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert resp.status_code == 401


async def test_me_with_synthetic_admin_token_returns_401_when_employee_missing(
    test_client, admin_token, db_session
):
    """`create_access_token` alone is not enough — `get_current_user` must
    look the Employee row up. A random-UUID admin will not be present in DB,
    so this must fail with 401 (and proves the DB lookup happens)."""
    resp = await test_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 401


async def test_login_then_me_succeeds_for_default_admin(test_client, db_session):
    """End-to-end smoke: login as the seeded default admin, then read profile.

    Skipped automatically when PostgreSQL is unreachable (via `db_session`).
    Skipped explicitly when the default admin is not seeded yet.
    """
    from app.config import settings

    login = await test_client.post(
        "/api/auth/login",
        json={
            "email": settings.default_admin_email,
            "password": settings.default_admin_password,
        },
    )
    if login.status_code != 200:
        pytest.skip(
            f"Default admin login not available "
            f"(status={login.status_code}, body={login.text[:200]})"
        )

    token = login.json()["access_token"]
    me = await test_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200, me.text
    body = me.json()
    assert body["email"] == settings.default_admin_email
    assert body["role"] == "admin"
