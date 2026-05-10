# Architecture

## System overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        On-Premise Server                         │
│                                                                  │
│  ┌──────────────────┐        ┌───────────────────────────────┐  │
│  │   Admin Portal   │        │      CMD Support API          │  │
│  │   (Next.js)      │──────▶ │        (FastAPI)              │  │
│  └──────────────────┘        │                               │  │
│                               │  /api/*   REST endpoints      │  │
│                               │  /mcp     MCP server          │  │
│                               │  /docs    Swagger UI          │  │
│                               └───────────────┬───────────────┘  │
│                                               │                  │
│  ┌────────────────┐  ┌──────────────┐        │                  │
│  │ Wiki Worker    │  │ Skill Worker │        │                  │
│  │ (arq)          │  │ (arq)        │        │                  │
│  │ · ingestion    │  │ · skill pkg  │        │                  │
│  │ · compilation  │  │   processing │        │                  │
│  └────────────────┘  └──────────────┘        │                  │
│                                               │                  │
│  ┌──────────────┐  ┌───────────┐  ┌────────┐│                  │
│  │  PostgreSQL  │  │   Redis   │  │ MinIO  ││                  │
│  │  + pgvector  │  │  (queue)  │  │(files) ││                  │
│  └──────────────┘  └───────────┘  └────────┘│                  │
└───────────────────────────────────────────────┼─────────────────┘
                                                │ MCP (HTTPS)
                               ┌────────────────┼────────────┐
                               │                │            │
                          Claude Desktop    Claude.ai    Any MCP
                          (employees)       (web)        client
```

---

## Components

### Admin Portal (`frontend/`)
Next.js application. Provides the UI for:
- Knowledge base and document management
- Wiki browser (three-panel: page tree, content, backlinks/outlinks)
- Workspace management and member roles
- RBAC configuration (departments, roles, permissions)
- Employee accounts and MCP token management
- AI Skills library
- Audit log

### CMD Support API (`app/`)
FastAPI application serving two protocols simultaneously:

**REST API** (`/api/*`) — used by the Admin Portal and direct integrations:
- Auth: JWT-based session for portal users
- Sources: document upload, URL ingestion, recompilation
- Wiki: page CRUD, drafts, revisions, graph
- Projects (Workspaces): member management, scoped sources and wiki
- RBAC: departments, employees, roles, permissions
- Skills: upload, version management, scope assignment
- Audit: activity log

**MCP Server** (`/mcp`) — used by Claude Desktop and other MCP clients:
- Auth: bearer token (MCP token per employee)
- Tools: wiki search/read, source drill-down, skill access
- All responses are filtered by the employee's permission scope

### Background Workers (`app/worker.py`)
Two arq (Redis-based) worker pools:

**Wiki Worker** (`WorkerSettings`):
- `ingest_file_task` — extract text and images from uploaded files
- `ingest_url_task` — scrape and extract text from URLs
- `compile_wiki_task` — run the LLM wiki agent to compile a source into wiki pages

**Skill Worker** (`SkillWorkerSettings`):
- `process_skill_task` — process uploaded skill packages

### LLM Wiki Agent (`app/ai/`)
The core compilation pipeline:

1. **Pre-analysis** (`wiki_analyzer.py`) — a cheap single LLM call that reads the first ~30K characters of a document and returns a structural map: document type, key entities, related existing wiki pages to update, new pages to create.

2. **Agent loop** (`wiki_agent.py`) — a tool-calling agent that reads the source, searches the existing wiki, and calls `create_page` / `update_page` tools to write or update wiki pages. Runs until the agent calls `finish()` or hits the turn limit.

3. **Agent tools** (`wiki_agent_tools.py`) — the tool catalog available to the agent: `read_wiki_index`, `read_wiki_page`, `search_wiki`, `read_source_excerpt`, `create_page`, `update_page`, `append_log`, `finish`.

---

## Data model

### Core entities

```
sources                    → uploaded documents (files or URLs)
  └── source_departments   → which departments can access a source

wiki_pages                 → compiled wiki articles
  ├── wiki_links           → [[wikilink]] graph edges between pages
  ├── wiki_page_drafts     → pending edits proposed by contributors
  └── wiki_page_revisions  → full version history (immutable snapshots)

knowledge_types            → categories (SOP, Product, HR Policy, ...)

departments                → org units for access scoping
employees                  → user accounts
  └── roles                → custom RBAC role with permission list

projects                   → workspaces (cross-functional contexts)
  ├── project_members      → workspace members with roles (viewer/contributor/editor/admin)
  └── project_sources      → sources linked to a workspace

skills                     → AI skill packages
  ├── skill_departments    → department scoping for skills
  └── skill_versions       → version history with storage paths

mcp_tokens                 → per-employee bearer tokens for MCP access
audit_log                  → immutable activity log
```

### Permission scoping

Every resource has a scope:
- `scope_type = "global"` — visible to anyone with the appropriate global permission
- `scope_type = "project", scope_id = <project_id>` — restricted to workspace members

This applies to: `sources`, `wiki_pages`, `skills`.

---

## Request flow

### Document upload → wiki compilation

```
POST /api/sources/upload
  → MinIO: store file
  → DB: create Source(status=pending)
  → Redis: enqueue ingest_file_task

Worker: ingest_file_task
  → Extract text (pdfplumber / python-docx / html2text)
  → Vision model: caption embedded images (optional)
  → DB: Source(status=processing)
  → Redis: enqueue compile_wiki_task

Worker: compile_wiki_task
  → wiki_analyzer: single LLM call, structural pre-analysis
  → wiki_agent loop:
      LLM calls tools (search_wiki, read_wiki_page, create_page, update_page)
      Each create/update writes a WikiPageRevision(change_type=agent_compile)
  → DB: Source(status=ready)
  → wiki_service.regenerate_index() + append_log()
```

### Employee Claude query → MCP response

```
Claude Desktop → POST /mcp (Bearer ark_xxx)
  → MCPAuthService.verify_token() → resolve employee identity + scope
  → Tool called (e.g. search_wiki)
      → filter wiki pages by employee's allowed knowledge types + dept
      → semantic search via pgvector
  → Return ranked results
```

### Wiki draft workflow

```
Contributor → POST /api/wiki/pages/{slug}/drafts
  → WikiPageDraft(status=pending) created
  → Editor notified (future: notification system)

Editor → GET /api/wiki/drafts (lists pending for their scope)
Editor → POST /api/wiki/drafts/{id}/approve
  → WikiPage.content_md updated
  → WikiPageRevision(change_type=draft_approved) created
  → Draft status → approved

Editor → POST /api/wiki/drafts/{id}/reject
  → reviewer_note required
  → Draft status → rejected
```

---

## Directory structure

```
arkon/
├── app/
│   ├── main.py               # FastAPI app, CORS, router registration, lifespan
│   ├── config.py             # Settings (pydantic-settings, reads from .env)
│   ├── database/
│   │   ├── models.py         # SQLAlchemy ORM models
│   │   └── __init__.py       # async_session_factory, get_db dependency
│   ├── routers/
│   │   ├── auth.py           # Login, me, change-password
│   │   ├── sources.py        # Document upload, ingestion, recompile
│   │   ├── wiki.py           # Wiki page CRUD, revisions, graph
│   │   ├── wiki_drafts.py    # Draft propose/approve/reject
│   │   ├── projects.py       # Workspace CRUD, members, sources, wiki
│   │   ├── skills.py         # AI skill upload and management
│   │   ├── rbac.py           # Departments, employees
│   │   ├── roles.py          # Role and permission management
│   │   ├── knowledge_types.py
│   │   ├── admin_settings.py # AI provider config
│   │   ├── audit.py          # Audit log
│   │   └── notes.py
│   ├── services/
│   │   ├── auth_service.py       # JWT, get_current_user, require_permission
│   │   ├── mcp_auth_service.py   # MCP token resolution
│   │   ├── permission_engine.py  # RBAC logic, scope resolution
│   │   ├── permissions.py        # Permission string constants
│   │   ├── wiki_service.py       # Wiki CRUD, draft/revision operations
│   │   ├── skill_service.py      # Skill CRUD, versioning
│   │   ├── storage_service.py    # MinIO wrapper
│   │   ├── audit_service.py      # log_audit()
│   │   └── kb_service.py         # Source extraction helpers
│   ├── ai/
│   │   ├── wiki_agent.py         # LLM agent loop (compile_source_with_agent)
│   │   ├── wiki_agent_tools.py   # Tool catalog for the wiki agent
│   │   ├── wiki_analyzer.py      # Pre-analysis single LLM call
│   │   └── providers/            # Provider-agnostic LLM/embedding/vision wrappers
│   └── mcp/
│       ├── server.py             # FastMCP server factory (create_mcp_server)
│       └── tools.py              # All MCP tools (register_tools)
├── frontend/
│   └── src/
│       ├── app/(portal)/         # Page routes (wiki, workspaces, knowledge, ...)
│       └── components/           # UI components
├── alembic/
│   └── versions/                 # Migration files (001 → 014)
├── docker-compose.yml
├── Dockerfile
├── .env.example
└── pyproject.toml
```

---

## AI provider support

All AI operations go through provider-agnostic wrappers in `app/ai/providers/`. Configured at runtime via the Admin Portal Settings.

| Capability | Providers |
|---|---|
| **Embedding** | Google (`text-embedding-004`), OpenAI, Voyage, Cohere, Ollama |
| **LLM** | Google (Gemini), OpenAI (GPT), Anthropic (Claude), Ollama |
| **Vision** | Google, OpenAI |

Switching providers requires only a settings change — no code changes.
