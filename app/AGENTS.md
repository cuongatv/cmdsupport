# app/ — Backend (FastAPI + arq + MCP)

## OVERVIEW
Single FastAPI app that mounts an MCP server on `/mcp` and REST routers under `/api/*`. Two arq Redis worker queues (wiki + skills) live alongside but boot independently. Provider-agnostic AI (Google / OpenAI / Anthropic / Ollama / Voyage / Cohere) selected at runtime from DB-backed settings — never from `.env`.

## TOP-LEVEL FILES
| File | Role |
|---|---|
| `main.py` | Entry point. Composes MCP lifespan + FastAPI lifespan, registers all routers (explicitly — no auto-discovery), seeds default admin, exposes `/health` + `/api/health`. |
| `config.py` | `pydantic-settings` infra config (DB / Redis / MinIO / S3 / CORS / JWT). **AI provider config is NOT here** — it lives in DB and is loaded via `services/config_service.py`. |
| `worker.py` | arq workers (`WorkerSettings` for wiki ingestion + `SkillWorkerSettings` for skill packages). Exports both. Adding a job = pick a queue, register the function in the correct `WorkerSettings.functions`. |

## STRUCTURE
```
app/
├── ai/         # LLM agent + provider wrappers — see app/ai/AGENTS.md
├── data/       # Static reference JSON (Vietnam provinces, VSIC industry codes)
├── database/   # SQLAlchemy models + session — see app/database/AGENTS.md
├── jobs/       # arq job functions (currently task notifications only)
├── mcp/        # FastMCP server + tools — see app/mcp/AGENTS.md
├── routers/    # FastAPI routers — see app/routers/AGENTS.md
├── schemas/    # Pydantic request/response models (currently tasks only)
├── services/   # Business logic — see app/services/AGENTS.md
└── utils/      # Tiny shared helpers (text.py only)
```

## CONVENTIONS
- **Routers do HTTP, services do logic, models do persistence.** Don't put DB queries in routers; don't put auth checks in models.
- **Permission decorators**: use `Depends(require_permission("X"))` from `services/auth_service.py`. Don't roll your own.
- **DB session injection**: routers get `db: AsyncSession = Depends(get_db)` from `app.database`. Services usually take `session` as their first arg.
- **Logging**: use `from loguru import logger` (already used everywhere). Don't `import logging`.
- **Errors**: raise `HTTPException(status_code=...)` from routers. Services raise plain Python exceptions; the router translates.

## ANTI-PATTERNS
- **Don't import `app.main`** from inside `services/` or `routers/` — circular. Lazy-import inside functions if you must (see `tests/conftest.py` for the pattern).
- **Don't bypass `app.ai.registry`** to call providers directly. The registry resolves the *currently configured* provider at call time.
- **Don't add startup work outside the `lifespan` block** in `main.py`. The MCP lifespan must wrap the FastAPI lifespan; breaking that order silently breaks MCP.
- **Don't add a router file without registering it** in `main.py`'s `app.include_router(...)` block. There is no auto-discovery.
- **Don't put AI keys / provider settings in `config.py` or `.env`.** That's a deliberate split — keys are encrypted-at-rest in DB.
