"""Smoke test: the FastAPI application module imports cleanly."""
from fastapi import FastAPI


def test_import_app_succeeds():
    from app.main import app

    assert isinstance(app, FastAPI)


def test_app_registers_routes():
    from app.main import app

    assert len(app.routes) > 0


def test_auth_me_route_is_registered():
    from app.main import app

    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/api/auth/me" in paths
    assert "/api/auth/login" in paths
