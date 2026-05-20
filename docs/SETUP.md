# Setup Guide

Two ways to run CMD Support: **Docker** (recommended for production) or **Development** (for local development and contributing).

---

## Option A — Docker (Production)

### Prerequisites
- Docker Engine 24+
- Docker Compose v2+
- An API key for your AI provider (Google, OpenAI, or Anthropic)

### 1. Clone and configure

```bash
git clone https://github.com/nduckmink/arkon.git
cd arkon
cp .env.example .env
```

Edit `.env`:

```env
# Required: generate a strong random secret
SECRET_KEY=<run: python -c "import secrets; print(secrets.token_urlsafe(32))">

# Required: admin account created on first startup
DEFAULT_ADMIN_EMAIL=admin@yourcompany.com
DEFAULT_ADMIN_PASSWORD=your-secure-password

# Required: MinIO password (must match MINIO_SECRET_KEY below)
MINIO_SECRET_KEY=your-minio-secret

# Optional: restrict CORS in production
CORS_ORIGINS=https://your-domain.com

# Required: your public API URL (used by the frontend)
NEXT_PUBLIC_API_URL=https://your-domain.com
```

> The full `.env.example` documents every available variable.

### 2. Start

```bash
docker compose up -d
```

This starts four containers:
| Container | Purpose |
|---|---|
| `cmd_api` | FastAPI backend + MCP server (port 5055) |
| `cmd_worker` | Background worker — document ingestion + wiki compilation |
| `cmd_worker_skills` | Background worker — AI skill processing |
| `cmd_frontend` | Next.js admin portal (port 3119) |

Workers start only after `cmd_api` passes its health check, so there is no race condition on startup.

> Note: you need to separately run PostgreSQL, Redis, and MinIO, or add them to `docker-compose.yml`. The included compose file assumes they are already available via the `DATABASE_URL`, `REDIS_HOST`, and `MINIO_ENDPOINT` env vars.

### 3. First login

Open **http://your-server:3119** and log in with the credentials from `.env`.

### 4. Configure AI providers

Go to **Settings** and configure:

| Setting | Required | Notes |
|---|---|---|
| **Embedding model** | Yes | Used for semantic wiki search. E.g. `text-embedding-004` (Google) |
| **LLM** | Yes | Used for wiki compilation. Choose a large-context model. |
| **Vision model** | No | Enables image captioning during PDF ingestion |

Recommended LLMs for wiki compilation (large context window):
- `gemini-2.5-pro` (Google) — best results
- `gpt-4o` (OpenAI)
- `claude-sonnet-4-5` or newer (Anthropic)

### 5. Run database migrations

```bash
docker exec cmd_api alembic upgrade head
```

> On first startup, the API runs migrations automatically before serving requests. You only need to run this manually after upgrading CMD Support.

---

## Option B — Development

### Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| Python | 3.11 – 3.14 | Backend runtime |
| Node.js | 20+ | Frontend (Next.js) |
| PostgreSQL | 15+ with pgvector | Main database |
| Redis | 7+ | Background job queue |
| MinIO | Latest | File storage |

### 1. Infrastructure

Start infrastructure services with Docker:

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

### 2. Configure environment

```bash
cp .env.example .env
```

For local development, the defaults in `.env.example` work out of the box except:

```env
SECRET_KEY=dev-only-not-for-production
DEFAULT_ADMIN_EMAIL=admin@cmdsupport.com
DEFAULT_ADMIN_PASSWORD=cmd@1234
MINIO_SECRET_KEY=minioadmin123
```

### 3. Python backend

```bash
# Create and activate a virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Run database migrations
alembic upgrade head
```

### 4. Frontend

```bash
cd frontend
npm install
```

Create `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:5055
```

### 5. Start all services (3 terminals)

**Terminal 1 — API server:**
```bash
uvicorn app.main:app --host 0.0.0.0 --port 5055 --reload
```

On first startup you should see:
```
SUCCESS  MinIO bucket ready
SUCCESS  Default admin created: admin@cmdsupport.com
SUCCESS  CMD Support MCP Server ready at /mcp
SUCCESS  CMD Support API started successfully
```

**Terminal 2 — Wiki worker:**
```bash
python -m arq app.worker.WorkerSettings
```

**Terminal 3 — Frontend:**
```bash
cd frontend
npm run dev
```

Open **http://localhost:3000**.

> Documents will stay at `pending` status until the worker is running.

---

## First steps after setup

### 1. Configure AI providers
Settings → configure embedding model, LLM, and vision model.

### 2. Create a department
Admin Portal → Departments → New Department.

### 3. Create a knowledge type
Admin Portal → Knowledge Types → New Type (e.g. "SOP", "Product Docs").

### 4. Upload a document
Knowledge Base → Upload → select file or paste URL → choose knowledge type → submit.

Watch the progress indicator. Once complete, click Wiki to browse the compiled pages.

### 5. Create an employee and generate an MCP token
Admin Portal → Employees → New Employee → assign department and role.

On the employee detail page, click **Generate Token** to create their MCP token.

### 6. Connect Claude Desktop
See [MCP & Claude](MCP.md) for the connection guide.

---

## Option C — Telegram Integration (optional)

This section is only needed if you want to use the **Telegram Task Bridge** feature. The rest of CMD Support works without it.

### 1. Create a bot with BotFather

1. Open Telegram and start a chat with `@BotFather`.
2. Send `/newbot`, choose a display name and a username (e.g. `CMDSupportBot`).
3. BotFather returns a Bot Token in the format `123456789:ABCDEF...` — copy it somewhere safe. **Don't share it or commit it to version control.**
4. **Set Privacy Mode:** send `/setprivacy` to BotFather, select your bot, choose **ENABLED**. This ensures the bot only receives messages that start with `/`, reducing noise in group chats.
5. **Allow group membership:** send `/setjoingroups` to BotFather and ensure it is enabled so the bot can be added to groups.

### 2. Generate a webhook secret

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Copy the output. You'll paste it into Admin Portal → Settings → Telegram Webhook Secret.

### 3. Configure in Admin Portal

1. Go to **Admin Portal → Settings → Telegram Integration**.
2. Toggle **Enable Telegram Integration** on.
3. Paste the Bot Token into **Telegram Bot Token**.
4. Paste the generated secret into **Telegram Webhook Secret**.
5. Choose delivery mode:
   - **Webhook** — requires a public HTTPS endpoint; lower latency.
   - **Long Polling** — no public endpoint needed; suitable for air-gapped or VPN-only deployments.
6. If using Webhook: enter your public URL (e.g. `https://cmd.yourcompany.com/api/integrations/telegram/webhook`) in the **Webhook URL** field, then click **Register Webhook**.
7. Click **Save**.

### 4. Add the bot to a Telegram group

In Telegram, open the group you want to link to a Squad, go to group settings → Add Member, and search for your bot's username. Add it as a member.

### 5. Bind the group to a Squad (`/bind`)

In Admin Portal, go to the Squad detail page → **Telegram** tab → click **Generate bind code**. Copy the `/bind CMD-XXXXX` code shown, then paste it into the Telegram group:

```
/bind CMD-XXXXX
```

The bot confirms the binding and sets the default TaskProject for tasks created from that group. The Telegram user who sends `/bind` must be a CMD Support admin of that Squad.

### 6. Link personal Telegram accounts (`/link`)

Each team member who wants to create or be assigned tasks from Telegram needs to link their account once. They should:

1. Go to **Admin Portal → Profile → MCP Tokens** and copy their personal token (`ark_xxxxxxxxxxxx`).
2. Open a private chat with the bot and send:

```
/link ark_xxxxxxxxxxxx
```

The bot confirms and their Telegram identity is linked. From this point, messages they send in bound groups are attributed to their CMD Support employee account.

### 7. Using the bot in a group

| Command | What it does |
|---|---|
| `/task <title>` | Create a task in the bound project |
| `/task @username <title>` | Create and assign in one step |
| `/assign @username <task-id>` | Assign an existing task |
| `/mytasks` | List your open tasks in the bound project |
| `/done <task-id>` | Move a task to the first workflow state with `group='done'` |
| `/help` | Show available commands |

Sender and assignee must both be active Squad members with linked Telegram identities. The bot rejects commands from unlinked or non-member accounts.

### Troubleshooting

| Issue | Solution |
|---|---|
| Bot not receiving messages | Check Privacy Mode is ENABLED in BotFather; confirm the bot is a group member |
| `/bind` rejected | The Telegram user sending `/bind` is not a Squad admin in CMD Support; check employee role |
| `/link` rejected | MCP token is invalid or expired; regenerate it from Admin Portal → Profile |
| Tasks not created | Confirm the bound Squad has a default TaskProject configured |
| Webhook not receiving updates | Verify the public HTTPS URL is reachable, webhook secret matches, and the certificate is valid |
| Messages delayed or not sent | Check that `cmd_worker_skills` container is running; inspect `telegram_outbox` table for `last_error` |
| Bot kicked from group | Group binding is disabled automatically; re-add the bot and re-run `/bind` |
| Webhook stuck after supergroup migration | Telegram auto-migrates groups to supergroups; re-register the webhook and re-bind the group. The `bot_status='migrated'` field in `telegram_group_bindings` marks affected rows |
| Rotate webhook secret | Generate a new secret, update it in Admin Portal → Settings, then click **Register Webhook** again |

---

## Environment variables reference

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | — | PostgreSQL connection string (asyncpg format) |
| `SECRET_KEY` | — | JWT signing secret. Must be changed in production. |
| `DEFAULT_ADMIN_EMAIL` | `admin@cmdsupport.com` | Admin account email (created on first startup) |
| `DEFAULT_ADMIN_PASSWORD` | `cmd@1234` | Admin account password |
| `MINIO_ENDPOINT` | `localhost:9000` | MinIO server address |
| `MINIO_ACCESS_KEY` | `minioadmin` | MinIO access key |
| `MINIO_SECRET_KEY` | — | MinIO secret key |
| `MINIO_BUCKET` | `cmd-support-files` | Bucket name for uploaded files |
| `MINIO_SECURE` | `false` | Use HTTPS for MinIO (`true` in production) |
| `REDIS_HOST` | `localhost` | Redis host |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_PASSWORD` | _(empty)_ | Redis password |
| `WORKER_MAX_JOBS` | `3` | Max concurrent background jobs |
| `CORS_ORIGINS` | `*` | Allowed CORS origins (comma-separated) |
| `NEXT_PUBLIC_API_URL` | `http://localhost:5055` | Public API URL (used by the browser) |
| `INTERNAL_API_URL` | `http://api:5055` | Internal API URL used by the Next.js server for proxying (Docker only) |

AI provider settings (embedding, LLM, vision, API keys) are configured through the Admin Portal → Settings, not in `.env`.

---

## Troubleshooting

| Issue | Solution |
|---|---|
| `connection refused` on port 5432 | PostgreSQL not running |
| `pgvector extension not found` | Use `pgvector/pgvector` Docker image |
| Documents stuck at `pending` | Wiki worker not running |
| Wiki pages not created after upload | Check LLM config in Settings; check worker logs |
| Frontend shows API error | Backend not running, or `NEXT_PUBLIC_API_URL` incorrect |
| CORS errors in browser | Add frontend URL to `CORS_ORIGINS` in `.env` |
| `requires Python 3.11` | Use `py -3.11 -m venv .venv` to select correct version |
| MCP connection refused | Ensure the API is accessible from outside (check firewall/proxy) |
