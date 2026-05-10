"""Performance / pagination guards for the native task list endpoint.

Acceptable limits (T32):
    * `GET /api/tasks` MUST cap `page_size` at 100. The router enforces this
      via `Query(default=20, ge=1, le=100)` in app/routers/tasks.py:353.
      Any request with `page_size > 100` is rejected with HTTP 422.
    * The kanban frontend uses `KANBAN_PAGE_SIZE = 100` (frontend/src/...) so
      the boundary is symmetric: frontend never asks for more than backend
      will return.
    * `total` in the paginated response MUST reflect the *un-capped* row count
      so clients can paginate or render counts correctly.

These tests run against the live Docker API container `cmd_api` at
http://localhost:5055 and follow the same pattern as
tests/api/test_tasks_api.py.
"""
from __future__ import annotations

import time
from typing import Any, AsyncIterator

import httpx
import pytest

pytestmark = pytest.mark.asyncio

BASE_URL = "http://localhost:5055"
ADMIN_EMAIL = "admin@cmdsupport.com"
ADMIN_PASSWORD = "cmd@1234"

# Acceptable upper bound enforced by the backend router. If you need to raise
# this, also raise `Query(le=...)` in app/routers/tasks.py and the frontend's
# KANBAN_PAGE_SIZE constant — keep them in lockstep.
MAX_PAGE_SIZE: int = 100


@pytest.fixture
async def api_client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        try:
            await client.get("/", timeout=5.0)
        except httpx.HTTPError as exc:
            pytest.skip(f"Docker API not reachable at {BASE_URL}: {exc!r}")
        yield client


@pytest.fixture
async def admin_headers(api_client: httpx.AsyncClient) -> dict[str, str]:
    resp = await api_client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if resp.status_code != 200:
        pytest.skip(f"Admin login unavailable: {resp.status_code} {resp.text[:200]}")
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _admin_user(api_client: httpx.AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    resp = await api_client.get("/api/auth/me", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _create_project(api_client: httpx.AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    user = await _admin_user(api_client, headers)
    suffix = str(time.time_ns())[-8:]
    resp = await api_client.post(
        "/api/tasks/projects",
        headers=headers,
        json={
            "name": f"Perf Pagination {suffix}",
            "description": "T32 pagination guard project",
            "identifier": f"P{suffix[-5:]}",
            "department_id": user["department_id"],
            "allow_any_employee": True,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _default_state(api_client: httpx.AsyncClient, headers: dict[str, str], project_id: str) -> dict[str, Any]:
    resp = await api_client.get(f"/api/tasks/projects/{project_id}/states", headers=headers)
    assert resp.status_code == 200, resp.text
    states = resp.json()
    assert states
    return states[0]


async def _seed_tasks(
    api_client: httpx.AsyncClient,
    headers: dict[str, str],
    project_id: str,
    state_id: str,
    count: int,
) -> None:
    for i in range(count):
        resp = await api_client.post(
            "/api/tasks",
            headers=headers,
            params={"task_project_id": project_id},
            json={
                "title": f"perf task {i}",
                "priority": "medium",
                "state_id": state_id,
                "assignee_ids": [],
                "label_ids": [],
            },
        )
        assert resp.status_code == 201, resp.text


async def test_page_size_above_cap_is_rejected(api_client, admin_headers):
    """Backend MUST reject page_size > MAX_PAGE_SIZE with HTTP 422.

    This is the structural guard. Even with no data, FastAPI's `Query(le=100)`
    validation should refuse the request before it ever reaches the service
    layer — preventing accidental unbounded responses.
    """
    project = await _create_project(api_client, admin_headers)
    resp = await api_client.get(
        "/api/tasks",
        headers=admin_headers,
        params={"task_project_id": project["id"], "page_size": MAX_PAGE_SIZE + 1},
    )
    assert resp.status_code == 422, resp.text


async def test_page_size_at_cap_is_accepted(api_client, admin_headers):
    """page_size == MAX_PAGE_SIZE is the accepted upper bound."""
    project = await _create_project(api_client, admin_headers)
    resp = await api_client.get(
        "/api/tasks",
        headers=admin_headers,
        params={"task_project_id": project["id"], "page_size": MAX_PAGE_SIZE},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["page_size"] == MAX_PAGE_SIZE
    assert len(body["items"]) <= MAX_PAGE_SIZE


async def test_response_cannot_exceed_max_page_size(api_client, admin_headers):
    """Even after seeding more than MAX_PAGE_SIZE rows the response
    cannot deliver more items than the cap, but `total` reflects all rows.

    Seeds MAX_PAGE_SIZE + 5 tasks and asks for the maximum allowed page_size.
    Verifies items length <= cap and total >= seeded count.
    """
    project = await _create_project(api_client, admin_headers)
    state = await _default_state(api_client, admin_headers, project["id"])

    seeded = MAX_PAGE_SIZE + 5
    await _seed_tasks(api_client, admin_headers, project["id"], state["id"], seeded)

    resp = await api_client.get(
        "/api/tasks",
        headers=admin_headers,
        params={"task_project_id": project["id"], "page_size": MAX_PAGE_SIZE},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["page_size"] == MAX_PAGE_SIZE
    assert len(body["items"]) <= MAX_PAGE_SIZE
    assert body["total"] >= seeded


async def test_pagination_returns_distinct_pages(api_client, admin_headers):
    """Pages MUST return distinct task ids (no overlap, no duplication)."""
    project = await _create_project(api_client, admin_headers)
    state = await _default_state(api_client, admin_headers, project["id"])
    await _seed_tasks(api_client, admin_headers, project["id"], state["id"], 5)

    page1 = await api_client.get(
        "/api/tasks",
        headers=admin_headers,
        params={"task_project_id": project["id"], "page": 1, "page_size": 2},
    )
    page2 = await api_client.get(
        "/api/tasks",
        headers=admin_headers,
        params={"task_project_id": project["id"], "page": 2, "page_size": 2},
    )
    assert page1.status_code == 200, page1.text
    assert page2.status_code == 200, page2.text

    ids1 = {item["id"] for item in page1.json()["items"]}
    ids2 = {item["id"] for item in page2.json()["items"]}
    assert ids1 and ids2
    assert ids1.isdisjoint(ids2)
