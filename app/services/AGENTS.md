# app/services/ — Business logic layer

## OVERVIEW
25 service modules. Pure-Python (no FastAPI imports), async-first, take an `AsyncSession` as their first argument. Routers call services; services call models + storage + AI registry. Anything reused across two routers belongs here.

## NOTABLE GROUPS
**Auth + permissions (5 files)** — `auth_service.py` (JWT, `get_current_user`, `require_permission`), `mcp_auth_service.py` (MCP bearer-token resolution), `permissions.py` (permission *string constants* — import from here, never literal), `permission_engine.py` (RBAC scope resolution), `policy_engine.py` (workspace/global scope filter), `rate_limit.py`.

**Task domain (12 files, ~100 KB)** — split deliberately by concern, NOT by entity:
- `task_service.py` — CRUD + status transitions
- `task_access_service.py` — visibility filters
- `task_attachment_service.py` — file upload/download
- `task_comment_service.py` — threaded comments
- `task_constants.py` — status / priority enums
- `task_dashboard_service.py` — aggregated views
- `task_filter_service.py` — query-string → SQL
- `task_notification_service.py` — task-event → notification fan-out
- `task_project_service.py` — task ↔ project membership
- `task_jobs.py` (in `app/jobs/`, not here) — arq scheduled scans

When adding task logic, **find the right `task_*` file first**. Don't add a 13th file unless the concern is genuinely new.

**Wiki + AI (3 files)** — `wiki_service.py` (page CRUD + drafts + revisions), `kb_service.py` (text/image extraction helpers used by ingestion), `source_outline.py` (assemble full text + outline before LLM call).

**Storage (2 files)** — `storage_service.py` (MinIO/S3 wrapper, signed URLs), `image_service.py` (extract embedded images for vision captions).

**Other** — `audit_service.py` (`log_audit()` — call from any state-changing op), `cmd_support_service.py` (BIDV advisory flow), `config_service.py` (DB-backed AI provider settings), `skill_service.py` (skill package versioning).

## CONVENTIONS
- **First arg is `session: AsyncSession`** for any function that touches the DB.
- **Return ORM models or dataclasses, not Pydantic schemas.** The router converts.
- **`log_audit(session, actor, action, target, details)` after every mutation.** Audit is append-only; never mutate `audit_log` rows.
- **Permission strings live in `permissions.py`.** Import the constant: `from app.services.permissions import WIKI_EDIT`. Never copy the string.

## ANTI-PATTERNS
- **Don't import `app.main` or `fastapi`** from a service. Services are HTTP-agnostic.
- **Don't catch and swallow exceptions silently.** Use `logger.exception(...)` and re-raise. The router decides the HTTP status.
- **Don't open a new `async_session_factory()` inside a service** if the caller already passed a session. Reuse the caller's transaction.
- **Don't add `_v2`, `_new`, `_old` suffixes.** Replace in place; commits give you history.
