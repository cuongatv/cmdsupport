import importlib

pytest = importlib.import_module("pytest")
pytestmark = pytest.mark.asyncio


async def test_status_without_token_returns_401(test_client, override_db_noop):
    resp = await test_client.get("/api/tasks/status")
    assert resp.status_code == 401


async def test_status_with_synthetic_admin_token_needs_db(test_client, admin_token, db_session):
    """With a valid JWT but synthetic (non-existent) admin, get_current_user returns 401.
    If DB is unavailable, this test is skipped via db_session fixture."""
    resp = await test_client.get(
        "/api/tasks/status",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    # Synthetic admin UUID doesn't exist in DB so returns 401
    assert resp.status_code == 401


async def test_status_with_real_admin_jwt_returns_200(test_client, db_session):
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
    resp = await test_client.get(
        "/api/tasks/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"native": True}


async def test_status_route_is_registered(test_client, override_db_noop):
    """The route exists — if we call it without auth we get 401, not 404."""
    resp = await test_client.get("/api/tasks/status")
    assert resp.status_code != 404
