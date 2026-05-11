# app/routers/ — FastAPI route handlers

## OVERVIEW
17 router modules. Each exports a single `router = APIRouter(prefix="/...", ...)` and is wired in `app/main.py` under the `/api` umbrella. **No auto-discovery** — adding a router means adding both the file *and* an `app.include_router(...)` line.

## ROUTER MAP
| File | Mount | Domain |
|---|---|---|
| `auth.py` | `/api/auth` | login / me / change-password (JWT) |
| `rbac.py` | `/api/rbac` | departments + employees |
| `roles.py` | `/api/roles` | custom RBAC roles + permission lists |
| `admin_settings.py` | `/api/admin/settings` | AI provider config (read/write encrypted DB rows) |
| `audit.py` | `/api/audit` | append-only activity log |
| `notifications.py` | `/api/notifications` | user notification feed |
| `sources.py` | `/api/sources` | document upload / URL ingest / recompile (+ arq enqueue) |
| `notes.py` | `/api/notes` | inline notes attached to sources |
| `wiki.py` | `/api/wiki` | wiki page CRUD + revisions + graph |
| `wiki_drafts.py` | `/api/wiki/drafts` | propose / approve / reject draft edits |
| `knowledge_types.py` | `/api/knowledge-types` | SOP / Product / HR Policy categories |
| `projects.py` | `/api/projects` | workspaces + members + scoped sources |
| `skills.py` | `/api/skills` | AI skill upload + version pinning |
| `cmd_support.py` | `/api/cmd-support` | BIDV CMD advisory queries |
| `tasks.py` | `/api/tasks` | native task system (largest router, 31 KB) |

## CONVENTIONS
- **One router per file**, exported as a module-level `router`.
- **Prefix on the `APIRouter`**, NOT on individual routes — keeps URLs visible in one place.
- **Tags** are added at registration time in `main.py`, not on `APIRouter()`. (Yes, both work — we picked one.)
- **Pagination**: query params `limit: int = 50, offset: int = 0`. Don't invent your own.
- **Permission checks**: `Depends(require_permission("perm.string"))` first, then DB work. Permission strings live in `services/permissions.py` — reuse, don't string-literal them.
- **Long handlers** (`tasks.py`, `projects.py`, `sources.py`) intentionally house the orchestration; the heavy lifting still lives in `app/services/task_*` etc.

## ANTI-PATTERNS
- **Don't mount routers at `/`** — every router belongs under `/api`.
- **Don't return SQLAlchemy models directly.** Always wrap in a Pydantic response schema (`app/schemas/` or inline) so async-lazy-load doesn't blow up serialization.
- **Don't add a router and forget `main.py`** — the file will silently never be reached. The CI lint won't catch it; only a missing endpoint will.
- **Don't reach across domains in a router.** If `tasks.py` needs project data, call `task_project_service`, don't query `Project` directly.
