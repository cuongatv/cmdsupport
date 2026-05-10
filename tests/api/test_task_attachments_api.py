"""T18 — integration tests for native task attachment API.

Runs against the Docker stack at ``http://localhost:5055`` (admin login
``admin@cmdsupport.com`` / ``cmd@1234``).  Each test scaffolds its own
project + task so they can be re-run idempotently.
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

# Mirrors ``app.services.task_constants.MAX_ATTACHMENT_BYTES`` (25 MiB).
MAX_ATTACHMENT_BYTES = 26_214_400


@pytest.fixture
async def api_client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60.0) as client:
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
            "name": f"T18 Attachments {suffix}",
            "description": "T18 attachment integration test project",
            "identifier": f"A{suffix[-5:]}",
            "department_id": user["department_id"],
            "allow_any_employee": True,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _default_state(
    api_client: httpx.AsyncClient,
    headers: dict[str, str],
    project_id: str,
) -> dict[str, Any]:
    resp = await api_client.get(
        f"/api/tasks/projects/{project_id}/states",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    states = resp.json()
    assert states
    return states[0]


async def _create_task(
    api_client: httpx.AsyncClient,
    headers: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    project = await _create_project(api_client, headers)
    state = await _default_state(api_client, headers, project["id"])
    resp = await api_client.post(
        "/api/tasks",
        headers=headers,
        params={"task_project_id": project["id"]},
        json={
            "title": "T18 attachment task",
            "description": "task created by attachment integration test",
            "priority": "medium",
            "state_id": state["id"],
            "assignee_ids": [],
            "label_ids": [],
        },
    )
    assert resp.status_code == 201, resp.text
    return project, resp.json()


async def test_upload_attachment_returns_201_dto_without_storage_key(
    api_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    _, task = await _create_task(api_client, admin_headers)

    resp = await api_client.post(
        f"/api/tasks/{task['id']}/attachments",
        headers=admin_headers,
        files={"file": ("notes.txt", b"hello attachment world", "text/plain")},
    )
    assert resp.status_code == 201, resp.text
    payload = resp.json()
    assert payload["task_id"] == task["id"]
    assert payload["filename"] == "notes.txt"
    assert payload["content_type"] == "text/plain"
    assert payload["size_bytes"] == len(b"hello attachment world")
    assert payload["uploaded_by_id"]
    assert "storage_key" not in payload, "storage_key MUST never be exposed"
    # presigned_url is intentionally not populated by the upload endpoint.
    assert payload.get("presigned_url") in (None, "")


async def test_upload_oversize_returns_413(
    api_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    _, task = await _create_task(api_client, admin_headers)

    oversized = b"x" * (MAX_ATTACHMENT_BYTES + 1)
    resp = await api_client.post(
        f"/api/tasks/{task['id']}/attachments",
        headers=admin_headers,
        files={
            "file": ("toobig.bin", oversized, "application/octet-stream"),
        },
        timeout=120.0,
    )
    assert resp.status_code == 413, resp.text
    assert "size" in resp.text.lower()


async def test_upload_bad_extension_returns_400(
    api_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    _, task = await _create_task(api_client, admin_headers)

    resp = await api_client.post(
        f"/api/tasks/{task['id']}/attachments",
        headers=admin_headers,
        files={
            "file": ("danger.exe", b"MZ\x00\x00", "application/octet-stream"),
        },
    )
    assert resp.status_code == 400, resp.text
    assert "extension" in resp.text.lower()


async def test_upload_to_deleted_task_is_rejected(
    api_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    _, task = await _create_task(api_client, admin_headers)

    delete_resp = await api_client.delete(
        f"/api/tasks/{task['id']}",
        headers=admin_headers,
    )
    assert delete_resp.status_code == 204, delete_resp.text

    resp = await api_client.post(
        f"/api/tasks/{task['id']}/attachments",
        headers=admin_headers,
        files={"file": ("late.txt", b"too late", "text/plain")},
    )
    assert resp.status_code in (400, 410), resp.text


async def test_upload_to_archived_project_returns_403(
    api_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    project, task = await _create_task(api_client, admin_headers)

    archive_resp = await api_client.delete(
        f"/api/tasks/projects/{project['id']}/archive",
        headers=admin_headers,
    )
    assert archive_resp.status_code == 200, archive_resp.text

    resp = await api_client.post(
        f"/api/tasks/{task['id']}/attachments",
        headers=admin_headers,
        files={"file": ("frozen.txt", b"archived", "text/plain")},
    )
    assert resp.status_code == 403, resp.text
    assert "archived" in resp.text.lower()


async def test_list_returns_uploaded_attachments(
    api_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    _, task = await _create_task(api_client, admin_headers)

    upload = await api_client.post(
        f"/api/tasks/{task['id']}/attachments",
        headers=admin_headers,
        files={"file": ("listed.txt", b"in the list", "text/plain")},
    )
    assert upload.status_code == 201, upload.text
    created = upload.json()

    listing = await api_client.get(
        f"/api/tasks/{task['id']}/attachments",
        headers=admin_headers,
    )
    assert listing.status_code == 200, listing.text
    items = listing.json()
    assert any(item["id"] == created["id"] for item in items)
    for item in items:
        assert "storage_key" not in item


async def test_download_returns_presigned_url(
    api_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    _, task = await _create_task(api_client, admin_headers)

    upload = await api_client.post(
        f"/api/tasks/{task['id']}/attachments",
        headers=admin_headers,
        files={"file": ("download.txt", b"presign me", "text/plain")},
    )
    assert upload.status_code == 201, upload.text
    attachment = upload.json()

    resp = await api_client.get(
        f"/api/tasks/{task['id']}/attachments/{attachment['id']}/download",
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["id"] == attachment["id"]
    assert payload["presigned_url"], "expected presigned_url to be populated"
    assert payload["presigned_url"].startswith("http"), payload["presigned_url"]
    assert "storage_key" not in payload


async def test_delete_attachment_removes_from_list(
    api_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    _, task = await _create_task(api_client, admin_headers)

    upload = await api_client.post(
        f"/api/tasks/{task['id']}/attachments",
        headers=admin_headers,
        files={"file": ("delete-me.txt", b"bye", "text/plain")},
    )
    assert upload.status_code == 201, upload.text
    attachment = upload.json()

    delete_resp = await api_client.delete(
        f"/api/tasks/{task['id']}/attachments/{attachment['id']}",
        headers=admin_headers,
    )
    assert delete_resp.status_code == 204, delete_resp.text

    listing = await api_client.get(
        f"/api/tasks/{task['id']}/attachments",
        headers=admin_headers,
    )
    assert listing.status_code == 200, listing.text
    assert all(item["id"] != attachment["id"] for item in listing.json())


async def test_download_unknown_attachment_returns_404(
    api_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    _, task = await _create_task(api_client, admin_headers)
    resp = await api_client.get(
        f"/api/tasks/{task['id']}/attachments/00000000-0000-0000-0000-000000000000/download",
        headers=admin_headers,
    )
    assert resp.status_code == 404, resp.text
