# tests/ — Backend pytest suite

## OVERVIEW
Centralized backend tests (NOT colocated with `app/`). 32 files across 8 sub-suites. Pytest + `pytest-asyncio` in `auto` mode. Smoke-friendly: tests that need Postgres skip cleanly when the DB is unreachable, so `pytest tests/smoke` works on a fresh checkout with zero infra.

> Frontend Playwright e2e is `frontend/tests/`, NOT here. See `frontend/AGENTS.md`.

## STRUCTURE
```
tests/
├── conftest.py     # 4 shared fixtures (see below) + autouse engine reset
├── smoke/          # No-infra: app import + auth wiring + token mint
├── api/            # In-process httpx ASGI hits against /api/tasks/* etc.
├── services/       # Pure service-layer unit tests (auth, permissions, task_*)
├── db/             # Schema-shape assertions for native_tasks
├── schemas/        # Pydantic request/response validation
├── integration/    # End-to-end task lifecycle + error flows (requires Postgres)
├── performance/    # Query-count + pagination perf budgets
└── security/       # RBAC + audit log assertions
```

## SHARED FIXTURES (`conftest.py`)
| Fixture | Use when |
|---|---|
| `_reset_engine_between_tests` (autouse) | Always on. Disposes the SQLAlchemy engine between tests so connections don't leak across event loops. |
| `test_client` | You want to hit the real FastAPI app via in-process ASGI (`httpx.AsyncClient(transport=ASGITransport(app))`). |
| `admin_token` | You need a JWT for an admin actor. Synthetic — does NOT touch the DB. |
| `db_session` | You need real DB. **Will `pytest.skip` if Postgres is down** — that's intentional, not a bug. |
| `override_db_noop` | You're testing 401/auth-fail paths that short-circuit before any DB query. Replaces `get_db` with a no-op generator. |

## CONVENTIONS
- **`pytest_asyncio.fixture` for async fixtures**, plain `pytest.fixture` for sync.
- **`pytestmark = pytest.mark.asyncio`** at the top of any module that's all-async — saves per-test decoration.
- **Test file naming**: `test_<thing>.py`. Function names: `test_<behaviour>_<expected>`.
- **One subject per file.** `test_task_service.py` covers only `task_service.py`.
- **Skip, don't xfail**, when infra is missing. `db_session` already does this; mirror the pattern for any new infra dependency.

## RUNNING
```bash
pytest                        # all (needs Docker stack for integration/db)
pytest tests/smoke -v         # zero-infra subset
pytest tests/services -v      # unit-style
pytest tests/api -k tasks     # quick filter
pytest -x --ff                # stop on first fail, run failures-first
```

## ANTI-PATTERNS
- **Don't import `app.main` at module top** in a smoke test — it forces full DB import on collection. Lazy-import inside the test (see `test_app_import.py`).
- **Don't `await session.commit()`** in a `db_session` test — the fixture rolls back on teardown. Committing breaks isolation.
- **Don't add a Jest/Vitest setup.** Frontend tests are Playwright-only by design.
- **Don't share state across tests via module-level mutables.** The autouse engine reset assumes per-test isolation.
- **Don't delete a failing security test** to make CI green. Open an issue and tag `security`.
