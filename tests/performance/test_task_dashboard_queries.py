"""Aggregate-query correctness for the task project dashboard.

Acceptable behaviour (T32):
    * `GET /api/tasks/projects/{id}/dashboard` MUST return SQL-aggregated
      counts. The implementation in app/services/task_dashboard_service.py
      uses `func.count + group_by + outerjoin` (see _aggregate_by_state and
      _aggregate_by_assignee). NO Python-side row counting.
    * `by_state` MUST contain ONE entry per state in the project — including
      states with zero tasks (LEFT OUTER JOIN guarantees this).
    * `total_tasks` MUST equal the count of non-deleted tasks in the project.
    * `overdue_count` MUST count only tasks whose due_date is in the past
      AND whose state group is NOT in ('done', 'cancelled').

These tests run against the live Docker API container `cmd_api` at
http://localhost:5055 and follow the same pattern as
tests/api/test_tasks_api.py.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator

import httpx
import pytest

pytestmark = pytest.mark.asyncio

BASE_URL = "http://localhost:5055"
ADMIN_EMAIL = "admin@cmdsupport.com"
ADMIN_PASSWORD = "cmd@1234"


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
            "name": f"Perf Dashboard {suffix}",
            "description": "T32 dashboard aggregate test project",
            "identifier": f"D{suffix[-5:]}",
            "department_id": user["department_id"],
            "allow_any_employee": True,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _list_states(api_client: httpx.AsyncClient, headers: dict[str, str], project_id: str) -> list[dict[str, Any]]:
    resp = await api_client.get(f"/api/tasks/projects/{project_id}/states", headers=headers)
    assert resp.status_code == 200, resp.text
    states = resp.json()
    assert states, "project must seed default states"
    return states


async def _create_task(
    api_client: httpx.AsyncClient,
    headers: dict[str, str],
    project_id: str,
    state_id: str,
    title: str,
    due_date: datetime | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": title,
        "priority": "medium",
        "state_id": state_id,
        "assignee_ids": [],
        "label_ids": [],
    }
    if due_date is not None:
        payload["due_date"] = due_date.isoformat()
    resp = await api_client.post(
        "/api/tasks",
        headers=headers,
        params={"task_project_id": project_id},
        json=payload,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_dashboard_by_state_includes_all_states(api_client, admin_headers):
    """`by_state` must list every state in the project, even empty ones."""
    project = await _create_project(api_client, admin_headers)
    states = await _list_states(api_client, admin_headers, project["id"])

    # Default project has 6 states (Backlog, Todo, In Progress, In Review, Done, Cancelled)
    resp = await api_client.get(
        f"/api/tasks/projects/{project['id']}/dashboard",
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert {row["state_id"] for row in body["by_state"]} == {s["id"] for s in states}
    # No tasks yet → every count is 0
    assert all(row["count"] == 0 for row in body["by_state"])
    assert body["total_tasks"] == 0
    assert body["overdue_count"] == 0


async def test_dashboard_aggregates_match_seeded_data(api_client, admin_headers):
    """Seed 5 tasks across 3 states; verify counts and total."""
    project = await _create_project(api_client, admin_headers)
    states = await _list_states(api_client, admin_headers, project["id"])

    by_group = {state["group"]: state for state in states}
    backlog = by_group["backlog"]
    in_progress = by_group["in_progress"]
    done = by_group["done"]

    # Seed: 2 in backlog, 2 in_progress, 1 done → total 5
    await _create_task(api_client, admin_headers, project["id"], backlog["id"], "b-1")
    await _create_task(api_client, admin_headers, project["id"], backlog["id"], "b-2")
    await _create_task(api_client, admin_headers, project["id"], in_progress["id"], "ip-1")
    await _create_task(api_client, admin_headers, project["id"], in_progress["id"], "ip-2")
    await _create_task(api_client, admin_headers, project["id"], done["id"], "d-1")

    resp = await api_client.get(
        f"/api/tasks/projects/{project['id']}/dashboard",
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    counts_by_state = {row["state_id"]: row["count"] for row in body["by_state"]}
    assert counts_by_state[backlog["id"]] == 2
    assert counts_by_state[in_progress["id"]] == 2
    assert counts_by_state[done["id"]] == 1

    # Other 3 default states (todo, review, cancelled) must still appear with count 0
    other_state_ids = {
        state["id"]
        for state in states
        if state["group"] not in ("backlog", "in_progress", "done")
    }
    for state_id in other_state_ids:
        assert counts_by_state[state_id] == 0

    assert body["total_tasks"] == 5


async def test_dashboard_overdue_count_excludes_terminal_states(api_client, admin_headers):
    """An overdue task in a terminal state (done/cancelled) MUST NOT count."""
    project = await _create_project(api_client, admin_headers)
    states = await _list_states(api_client, admin_headers, project["id"])
    by_group = {state["group"]: state for state in states}

    past = datetime.now(timezone.utc) - timedelta(days=2)

    # Overdue + non-terminal → counts (in_progress)
    await _create_task(
        api_client, admin_headers, project["id"], by_group["in_progress"]["id"],
        "overdue-active", due_date=past,
    )
    # Overdue + terminal → excluded (done)
    await _create_task(
        api_client, admin_headers, project["id"], by_group["done"]["id"],
        "overdue-done", due_date=past,
    )
    # Overdue + terminal → excluded (cancelled)
    await _create_task(
        api_client, admin_headers, project["id"], by_group["cancelled"]["id"],
        "overdue-cancelled", due_date=past,
    )

    resp = await api_client.get(
        f"/api/tasks/projects/{project['id']}/dashboard",
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["overdue_count"] == 1, body
    assert body["total_tasks"] == 3
