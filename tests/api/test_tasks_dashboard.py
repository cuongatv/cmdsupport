"""Integration tests for the task project dashboard aggregation endpoint (T16)."""
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
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=20.0) as client:
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
            "name": f"Dashboard {suffix}",
            "description": "T16 dashboard test project",
            "identifier": f"D{suffix[-5:]}",
            "department_id": user["department_id"],
            "allow_any_employee": True,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _list_states(
    api_client: httpx.AsyncClient, headers: dict[str, str], project_id: str
) -> list[dict[str, Any]]:
    resp = await api_client.get(f"/api/tasks/projects/{project_id}/states", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _create_task(
    api_client: httpx.AsyncClient,
    headers: dict[str, str],
    project_id: str,
    state_id: str,
    *,
    title: str = "T16 task",
    priority: str = "medium",
    due_date: datetime | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "title": title,
        "priority": priority,
        "state_id": state_id,
        "assignee_ids": [],
        "label_ids": [],
    }
    if due_date is not None:
        body["due_date"] = due_date.isoformat()
    resp = await api_client.post(
        "/api/tasks",
        headers=headers,
        params={"task_project_id": project_id},
        json=body,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_dashboard_returns_correct_state_counts(api_client, admin_headers):
    project = await _create_project(api_client, admin_headers)
    states = await _list_states(api_client, admin_headers, project["id"])
    by_group = {state["group"]: state for state in states}

    # Create 2 tasks in 'todo', 1 task in 'in_progress', 1 in 'done'
    await _create_task(api_client, admin_headers, project["id"], by_group["todo"]["id"], title="todo-1")
    await _create_task(api_client, admin_headers, project["id"], by_group["todo"]["id"], title="todo-2")
    await _create_task(api_client, admin_headers, project["id"], by_group["in_progress"]["id"], title="ip-1")
    await _create_task(api_client, admin_headers, project["id"], by_group["done"]["id"], title="done-1")

    resp = await api_client.get(
        f"/api/tasks/projects/{project['id']}/dashboard", headers=admin_headers
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()

    assert payload["total_tasks"] == 4

    counts_by_group = {item["group"]: item["count"] for item in payload["by_state"]}
    assert counts_by_group["todo"] == 2
    assert counts_by_group["in_progress"] == 1
    assert counts_by_group["done"] == 1
    assert counts_by_group["backlog"] == 0
    assert counts_by_group["review"] == 0
    assert counts_by_group["cancelled"] == 0

    # All default states present even when empty.
    assert {item["state_name"] for item in payload["by_state"]} >= {
        state["name"] for state in states
    }


async def test_dashboard_overdue_count_correct(api_client, admin_headers):
    project = await _create_project(api_client, admin_headers)
    states = await _list_states(api_client, admin_headers, project["id"])
    by_group = {state["group"]: state for state in states}

    now = datetime.now(timezone.utc)

    # Active overdue task: must be counted.
    await _create_task(
        api_client,
        admin_headers,
        project["id"],
        by_group["todo"]["id"],
        title="overdue-active",
        due_date=now - timedelta(days=2),
    )
    # Active overdue task in another non-terminal state.
    await _create_task(
        api_client,
        admin_headers,
        project["id"],
        by_group["in_progress"]["id"],
        title="overdue-in-progress",
        due_date=now - timedelta(hours=3),
    )
    # Overdue but already done — must NOT count.
    await _create_task(
        api_client,
        admin_headers,
        project["id"],
        by_group["done"]["id"],
        title="overdue-done",
        due_date=now - timedelta(days=10),
    )
    # Overdue but cancelled — must NOT count.
    await _create_task(
        api_client,
        admin_headers,
        project["id"],
        by_group["cancelled"]["id"],
        title="overdue-cancelled",
        due_date=now - timedelta(days=10),
    )
    # Future due — not overdue, but should appear in due_this_week.
    await _create_task(
        api_client,
        admin_headers,
        project["id"],
        by_group["todo"]["id"],
        title="future-soon",
        due_date=now + timedelta(days=2),
    )
    # No due date — not overdue.
    await _create_task(
        api_client,
        admin_headers,
        project["id"],
        by_group["todo"]["id"],
        title="no-due",
    )

    resp = await api_client.get(
        f"/api/tasks/projects/{project['id']}/dashboard", headers=admin_headers
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()

    assert payload["overdue_count"] == 2

    due_titles = {item["title"] for item in payload["due_this_week"]}
    assert "future-soon" in due_titles
    assert "overdue-active" not in due_titles  # past due is not "this week"
    assert "overdue-done" not in due_titles
    assert "no-due" not in due_titles

    # Due-soon items expose the lightweight shape only.
    for item in payload["due_this_week"]:
        assert set(item.keys()) == {"id", "title", "priority", "due_date", "state_name"}


async def test_empty_project_dashboard_returns_zeros(api_client, admin_headers):
    project = await _create_project(api_client, admin_headers)

    resp = await api_client.get(
        f"/api/tasks/projects/{project['id']}/dashboard", headers=admin_headers
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()

    assert payload["total_tasks"] == 0
    assert payload["overdue_count"] == 0
    assert payload["due_this_week"] == []
    assert payload["by_assignee"] == []

    # Default states are returned with zero counts.
    assert len(payload["by_state"]) >= 1
    assert all(item["count"] == 0 for item in payload["by_state"])
