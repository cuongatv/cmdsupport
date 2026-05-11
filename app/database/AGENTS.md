# app/database/ — SQLAlchemy models + session

## OVERVIEW
Three files, one *very* large. PostgreSQL + pgvector via `asyncpg`. Sessions are async; Alembic owns the schema; this directory owns the Python types.

## FILES
| File | Size | Role |
|---|---|---|
| `__init__.py` | 1 KB | Builds `engine`, `async_session_factory`, and the `get_db` FastAPI dependency. **Import these from here, not from anywhere else.** |
| `models.py` | **48 KB** | Every ORM model in one file: `Source`, `WikiPage`, `WikiPageDraft`, `WikiPageRevision`, `WikiLink`, `Project`, `ProjectMember`, `Department`, `Employee`, `Role`, `Skill`, `SkillVersion`, `KnowledgeType`, `Task`, `TaskComment`, `TaskAttachment`, `Notification`, `AuditLog`, `MCPToken`, … |
| `repository.py` | 2 KB | A thin handful of generic helpers (e.g. existence checks). Most queries live in `app/services/*` — don't grow this file into a god-object. |

## WORKING WITH `models.py`
- It is intentionally one file because Alembic autogenerate works best from a single metadata, and our cross-table relationships (workspaces ⇄ wiki ⇄ skills ⇄ permissions) aren't cleanly separable. **Resist the urge to split it** — earlier attempts produced circular-import knots.
- Search by class name (e.g. `class Task`) — file is alphabetized loosely by domain (sources → wiki → projects → rbac → skills → tasks → audit).
- Adding a column: edit the model → `alembic revision --autogenerate -m "..."` from repo root → review the generated migration → commit both.
- Adding a model: same flow, plus add the import to `__init__.py` if anyone outside `models.py` needs it directly.

## CONVENTIONS
- **Async sessions everywhere.** Every query is `await session.execute(select(...))`, never `.query()`.
- **`AsyncSession` only.** Don't import `Session` from sqlalchemy.orm.
- **`scope_type` + `scope_id` pattern**: `sources`, `wiki_pages`, `skills` use this for global-vs-workspace scoping. Mirror it on any new resource that needs the same distinction.
- **Soft-delete is rare** — most models hard-delete. Check the model before assuming a `deleted_at` column.

## ANTI-PATTERNS
- **Don't query inside a model class.** Classmethod query helpers belong in `services/`, not on the model.
- **Don't use the sync `Session`** anywhere. Tests use `AsyncSession` too (see `tests/conftest.py`).
- **Don't `await session.commit()` inside a service** if the caller is going to commit. Commit at the request boundary (router) unless you're enqueuing an arq job that must see the row.
- **Don't edit a merged Alembic migration** to fix a model bug — write a new migration. The `001..018` series is sealed.
