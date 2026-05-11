# PROJECT KNOWLEDGE BASE

**Generated:** 2026-05-11 (UTC)
**Commit:** `ddb11a2`
**Branch:** `main`

## OVERVIEW
**CMD Support** (formerly `arkon`) — on-prem Enterprise AI Knowledge Hub for BIDV. FastAPI backend exposes REST + MCP simultaneously; Next.js 16 portal; PostgreSQL+pgvector, Redis (arq), MinIO. Docs are *compiled* into a wiki by an LLM agent, then served to Claude Desktop via MCP.

## STRUCTURE
```
arkon/
├── app/             # Backend: FastAPI + arq workers + MCP server (Python 3.11-3.14)
├── frontend/        # Next.js 16 portal (App Router, React 19, Tailwind 4)
├── alembic/         # 19 numbered migrations (001..018) — see alembic/AGENTS.md
├── tests/           # Pytest, 8 sub-suites: api / db / integration / performance /
│                    #   schemas / security / services / smoke (NOT colocated)
├── infra/aws/       # Terraform modules — see infra/aws/README.md (12KB, self-documenting)
├── docs/            # Product/architecture docs (referenced by README)
├── scripts/         # backup.ps1 / restore.ps1 (Windows PowerShell)
├── alembic.ini      # Alembic config (script_location=alembic)
├── docker-compose.yml  # 6 services: postgres, redis, minio, api, worker, worker_skills, frontend
├── Dockerfile       # Backend image (single-stage, python:3.12-slim)
├── pyproject.toml   # Backend deps + ruff/pytest config (no setup.py, no requirements.txt)
└── .env.example     # ALL infra config; AI provider config lives in DB (Admin Portal)
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Backend startup, router wiring | `app/main.py` | mounts MCP at `/mcp`, REST under `/api` |
| Backend infra config | `app/config.py` | pydantic-settings, reads `.env`; AI config NOT here |
| Background jobs entry | `app/worker.py` | exports `WorkerSettings` (wiki) + `SkillWorkerSettings` |
| MCP server / Claude tools | `app/mcp/server.py` + `app/mcp/tools.py` | tools.py is 40KB — see `app/mcp/AGENTS.md` |
| LLM wiki compilation pipeline | `app/ai/wiki_agent.py`, `wiki_compiler.py`, `wiki_analyzer.py` | LLM-prompt-heavy; treat string blocks as prompts, not code |
| All ORM models | `app/database/models.py` | **48 KB single file** — see `app/database/AGENTS.md` |
| Frontend route shell | `frontend/src/app/layout.tsx` | App Router root |
| Frontend HTTP client | `frontend/src/lib/api.ts` | every fetch goes through `api()` — never use raw `fetch` |
| Frontend auth state | `frontend/src/lib/auth.tsx` | provider + permission helpers |
| Add a DB column | edit `app/database/models.py` → `alembic revision --autogenerate -m "..."` → review → commit |
| Add a REST endpoint | new file in `app/routers/`, register in `app/main.py` (NOT auto-discovered) |
| Add an MCP tool | `app/mcp/tools.py` `register_tools()` |
| Run a single test | `pytest tests/services/test_task_service.py -v` |

## CONVENTIONS (project-specific only)
- **Python**: ruff `select = ["E","F","I"]`, `ignore = ["E501"]`, line-length 88. Use **absolute imports** (`from app.services.x import y`). All DB/IO is `async/await`. Type-hint public functions.
- **TypeScript**: no `any` unless unavoidable. Components in PascalCase, files in kebab-case. Tailwind tokens come from `DESIGN.md` (BIDV teal `#2D8380`).
- **HTTP from frontend**: always use `api()` from `src/lib/api.ts`. Browser uses same-origin `/api/*`; Next.js rewrites them to the API container (`http://api:5055` in prod, `http://127.0.0.1:5055` in dev).
- **Migrations**: every model change ships with `alembic revision --autogenerate -m "short msg"`. Numbered prefix (NNN_) is mandatory — see `alembic/AGENTS.md`. Never edit a merged migration.
- **Commits**: Conventional Commits (`feat(api): ...`, `fix(worker): ...`). Squash-merge to `main`.
- **Volumes**: docker-compose volumes keep the `arkon_*` prefix even after the rename to CMD Support — preserves existing pilot data. Don't "fix" them.

## ANTI-PATTERNS (THIS PROJECT)
- **Do NOT use `mcp__claude-in-chrome__*` tools.** Use the gstack `/browse` skill for any browser work.
- **Do NOT add `as any`, `@ts-ignore`, `@ts-expect-error`** to satisfy the typechecker. `next.config.ts` already sets `typescript.ignoreBuildErrors: true` because CI runs `tsc --noEmit` separately — don't pile suppression on top.
- **Do NOT call `fetch` directly from frontend code.** Use `api()` so auth + base-URL handling stays consistent.
- **Do NOT translate wiki content.** The LLM agent prompts (in `app/ai/wiki_*.py`) explicitly forbid translating body text — pages must be in the source document's language (Vietnamese stays Vietnamese, English stays English).
- **Do NOT edit a merged Alembic migration**, including the `001..014` series and the `015_rename_admin_to_cmdsupport.py` rename. Add a new migration instead.
- **Do NOT register new routers via auto-discovery.** Wire them explicitly in `app/main.py`.
- **Do NOT commit `.env`, MinIO secrets, JWT `SECRET_KEY`, or AI provider API keys.** AI keys live in the DB (encrypted with `SECRET_KEY`).
- The two giant `session-ses_*.md` files in repo root are agent transcripts, **not** project docs. Don't read them for context; don't edit them.

## UNIQUE STYLES
- **Bilingual codebase**: README/CONTRIBUTING/comments mix English with Vietnamese (e.g. `app/data/provinces_vn_2025.json`, BIDV branding in `DESIGN.md`). Both are first-class.
- **Dual-protocol API**: one FastAPI app serves REST (`/api/*`) AND MCP (`/mcp`). Lifespans are composed (see `app/main.py` lines 58–86) — adding async startup work means wrapping `mcp_http_app.lifespan(app)`.
- **AI providers are runtime-configured**, not env-configured. Settings live in PostgreSQL and are managed via Admin Portal → Settings. `app/ai/registry.py` resolves the active provider per call.
- **Two arq queues** (`WorkerSettings`, `SkillWorkerSettings`) — adding a job means picking the right queue and exporting it from `app/worker.py`.

## COMMANDS
```bash
# Local stack (everything)
docker compose up -d
docker compose up -d --build           # after Dockerfile or pyproject changes

# Backend only (host, requires .venv with pip install -e ".[dev]")
uvicorn app.main:app --host 0.0.0.0 --port 5055 --reload
python -m arq app.worker.WorkerSettings
alembic upgrade head
alembic revision --autogenerate -m "short message"
ruff check app/ alembic/
ruff format app/ alembic/
pytest                                  # all backend tests
pytest tests/smoke -v                   # smoke subset (no Postgres needed)

# Frontend
cd frontend
npm run dev                             # http://localhost:3000
npm run build
npm run lint
npx tsc --noEmit                        # CI runs this; next build skips it
npm run test:e2e                        # Playwright; requires Docker stack on :3119

# Backups (Windows)
powershell .\scripts\backup.ps1
powershell .\scripts\restore.ps1 -BackupDir .\backups\YYYYMMDD_HHMMSS
```

## NOTES
- **CLAUDE.md** in this repo documents the `rtk` token-saving prefix; `rtk` is **not installed by default** on this Windows host. Run plain `git`, `pytest`, etc. unless you confirm `rtk` is on PATH.
- **Default ports**: API 5055, Frontend 3119 (mapped from container 3000), Postgres 5432, Redis 6379, MinIO 9000/9001.
- **Default admin** is seeded on first startup from `DEFAULT_ADMIN_EMAIL` / `DEFAULT_ADMIN_PASSWORD` (`.env`). The lifespan logs a warning if `SECRET_KEY` or admin password are still defaults — heed it before deploy.
- **CI** is a single workflow `.github/workflows/deploy.yml`: backend `ruff check`, frontend `lint` + `tsc --noEmit`, then SSH `git reset --hard origin/main && docker compose up -d --build`. **It does not run tests.** Tests are local/dev-only today.
- **infra/aws/.terraform/providers/** contains 700 MB+ of provider binaries that are gitignored on most systems — if you cloned them by accident, do not commit changes inside that path.
