# CMD Support — How to Run (Development)

## Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| Python | 3.11 — 3.14 | Backend runtime |
| Node.js | 20+ | Frontend (Next.js) |
| PostgreSQL | 15+ | Main database (with pgvector extension) |
| Redis | 7+ | Background job queue |
| MinIO | Latest | S3-compatible file storage |

## 1. Infrastructure

Start PostgreSQL, Redis, and MinIO. If you have Docker:

```bash
# PostgreSQL with pgvector
docker run -d --name arkon-pg \
  -e POSTGRES_USER=arkon \
  -e POSTGRES_PASSWORD=arkon_secret \
  -e POSTGRES_DB=cmd_support \
  -p 5432:5432 \
  pgvector/pgvector:pg16

# Redis
docker run -d --name arkon-redis -p 6379:6379 redis:7-alpine

# MinIO
docker run -d --name arkon-minio \
  -e MINIO_ROOT_USER=minioadmin \
  -e MINIO_ROOT_PASSWORD=minioadmin123 \
  -p 9000:9000 -p 9001:9001 \
  minio/minio server /data --console-address ":9001"
```

## 2. Environment

```bash
cp .env.example .env
```

Minimum values to set in `.env`:

```env
SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_urlsafe(32))">
DEFAULT_ADMIN_EMAIL=admin@yourcompany.com
DEFAULT_ADMIN_PASSWORD=change-this-password
MINIO_SECRET_KEY=minioadmin123   # match your MinIO password above
```

## 3. Install Dependencies

```bash
# Create virtual environment
python -m venv .venv

# Activate
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install
pip install -e ".[dev]"
```

## 4. Database Migration

```bash
alembic upgrade head
```

> Creates: `sources`, `wiki_pages`, `wiki_links`, `knowledge_types`, `departments`,
> `employees`, `knowledge_scopes`, `contacts`, `notes`, `app_config`, and more.
>
> Also seeds 5 default knowledge types: General, SOP, Product, Project, Customer.

## 5. Install Frontend

```bash
cd frontend
npm install
```

Create `frontend/.env.local`:
```env
NEXT_PUBLIC_API_URL=http://localhost:5055
```

## 6. Start Services

You need **4 terminals**.

### Terminal 1: API Server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 5055 --reload
```

On first startup, CMD Support will:
- Create the MinIO bucket if it doesn't exist
- **Auto-create the default admin account** from `.env` (if no admin exists yet)

You should see:
```
SUCCESS  Default admin created: admin@cmdsupport.com
SUCCESS  CMD Support MCP Server ready at /mcp
SUCCESS  CMD Support API started successfully
```

### Terminal 2: Wiki Worker

```bash
python -m arq app.worker.WorkerSettings
```

Processes document ingestion: text extraction, image captioning, and LLM wiki compilation. Documents stay at `pending` until this is running.

### Terminal 3: Skills Worker

```bash
python -m arq app.worker.SkillWorkerSettings
```

Handles AI skill package processing. Required if you use the Skills feature.

### Terminal 4: Frontend

```bash
cd frontend
npm run dev
```

Open http://localhost:3000 — log in with the admin credentials from `.env`.

## 7. Configure AI Providers

After first login, go to **Admin Portal → Settings** and configure:

- **Embedding model** — required for wiki page search (e.g. `text-embedding-004` / Google)
- **LLM** — required for wiki compilation; choose a model with a large context window (e.g. `gemini-2.5-pro`, `gpt-4o`, `claude-sonnet-4-5`)
- **Vision model** — optional, enables image captioning during ingestion

Without embedding + LLM config, document uploads will queue but wiki compilation will fail.

## 8. Verify

### API Health

```
http://localhost:5055/
```

### API Docs (Swagger)

```
http://localhost:5055/docs
```

### Login

```bash
curl -X POST http://localhost:5055/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@cmdsupport.com", "password": "cmd@1234"}'
```

Response:
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user": {
    "id": "...",
    "name": "Admin",
    "email": "admin@cmdsupport.com",
    "role": "admin"
  }
}
```

Use the `access_token` as `Authorization: Bearer <token>` for all admin API calls.

## 9. API Overview

### Auth
| Method | Path | Description |
|---|---|---|
| POST | `/api/auth/login` | Login (email + password) |
| GET | `/api/auth/me` | Current user profile |
| POST | `/api/auth/change-password` | Change password |

### Admin (requires `role=admin`)
| Method | Path | Description |
|---|---|---|
| GET/PUT | `/api/settings` | Provider config (AI keys, models) |
| CRUD | `/api/departments` | Manage departments |
| CRUD | `/api/employees` | Manage employees |
| POST/DELETE | `/api/employees/:id/token` | Generate/revoke MCP token |
| CRUD | `/api/knowledge-types` | Manage knowledge types |
| CRUD | `/api/scopes` | Manage knowledge scopes |
| CRUD | `/api/sources` | Manage documents |
| POST | `/api/sources/upload` | Upload a file |
| POST | `/api/sources/url` | Add a URL source |
| POST | `/api/sources/:id/recompile` | Re-run wiki compilation for a source |
| CRUD | `/api/contacts` | Manage contacts |

### Wiki (requires login)
| Method | Path | Description |
|---|---|---|
| GET | `/api/wiki/pages` | List wiki pages (filterable) |
| GET | `/api/wiki/pages/:slug` | Get a wiki page with backlinks |
| GET | `/api/wiki/index` | `_index` catalog page |
| GET | `/api/wiki/log` | `_log` chronological log |
| GET | `/api/wiki/graph` | Graph nodes + edges (full or neighborhood) |

### MCP (Claude Desktop)
| Path | Auth | Description |
|---|---|---|
| `/mcp` | `Bearer ark_xxx` (MCP token) | MCP endpoint for Claude Desktop |

## 10. Connect Claude Desktop

After generating an MCP token for an employee, add to Claude Desktop config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "cmd_support": {
      "url": "http://localhost:5055/mcp",
      "headers": {
        "Authorization": "Bearer ark_xxxx..."
      }
    }
  }
}
```

## Troubleshooting

| Issue | Solution |
|---|---|
| `connection refused` on port 5432 | PostgreSQL is not running |
| `pgvector extension not found` | Use `pgvector/pgvector` Docker image, or install pgvector manually |
| `No admin created` on startup | Check `DEFAULT_ADMIN_EMAIL` / `DEFAULT_ADMIN_PASSWORD` in `.env` |
| Documents stuck at `pending` | Wiki worker not running — start Terminal 2 |
| Wiki pages not created after upload | Check LLM provider config in Settings; check worker logs for errors |
| Skills not processing | Skills worker not running — start Terminal 3 |
| Frontend shows "API Error" | Backend not running, or `NEXT_PUBLIC_API_URL` incorrect in `frontend/.env.local` |
| CORS errors in browser | Add `http://localhost:3000` to `CORS_ORIGINS` in backend `.env` |
| `requires Python 3.11` error | Use `py -3.11 -m venv .venv` to create venv with correct version |
