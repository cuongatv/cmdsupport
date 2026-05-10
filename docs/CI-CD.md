# CI/CD Setup Guide

CMD Support uses **GitHub Actions** to lint code and deploy to a single production server via SSH.

Workflow file: [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml)

---

## Pipeline Overview

```
push to main  ──►  lint-backend (ruff)  ──┐
                                          ├──►  deploy (SSH → server)
              ──►  lint-frontend (eslint + tsc)  ──┘
```

| Job             | Trigger                  | Purpose                                          |
| --------------- | ------------------------ | ------------------------------------------------ |
| `lint-backend`  | every push to `main`     | `ruff check` over `app/` and `alembic/`          |
| `lint-frontend` | every push to `main`     | `npm run lint` + `tsc --noEmit` inside `frontend/` |
| `deploy`        | push to `main` (only)    | SSH to server, `git pull`, `docker compose up`   |

The `deploy` job runs **only after both lint jobs pass**.
You can also re-run a deploy manually via **Actions → CI/CD → Run workflow**.

---

## Required GitHub Secrets

Go to **Repository → Settings → Secrets and variables → Actions** and add:

| Secret        | Description                                              | Example                |
| ------------- | -------------------------------------------------------- | ---------------------- |
| `SERVER_IP`   | Public IP or hostname of the production server           | `123.45.67.89`         |
| `SERVER_USER` | SSH user that owns the project directory                 | `ubuntu`               |
| `SERVER_KEY`  | **Private** SSH key (whole file, including BEGIN/END)    | `-----BEGIN OPENSSH...`|

> The workflow assumes the project lives at `/home/<SERVER_USER>/arkon` on the server.
> If you use a different path, edit `APP_DIR` in `.github/workflows/deploy.yml`.

---

## One-Time Server Setup

Do this **once** on the production server before the first deploy.

### 1. Install Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# log out and back in so the group change takes effect
```

### 2. Generate a deploy SSH key (on your laptop)

```bash
ssh-keygen -t ed25519 -f ~/.ssh/arkon_deploy -C "github-actions-arkon" -N ""
```

This creates two files:
- `arkon_deploy`     → **private** key (paste into `SERVER_KEY` secret)
- `arkon_deploy.pub` → **public** key (install on the server below)

### 3. Authorize the key on the server

```bash
# on the server, as SERVER_USER
mkdir -p ~/.ssh
chmod 700 ~/.ssh
echo "<contents of arkon_deploy.pub>" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

Test from your laptop:
```bash
ssh -i ~/.ssh/arkon_deploy <SERVER_USER>@<SERVER_IP> "echo ok"
```

### 4. Clone the repo

```bash
cd ~
git clone https://github.com/<owner>/arkon.git
cd arkon
```

If the repo is private, configure a deploy key or use HTTPS with a personal token.

### 5. Create `.env`

```bash
cp .env.example .env
nano .env   # fill in SECRET_KEY, DEFAULT_ADMIN_*, NEXT_PUBLIC_API_URL, etc.
```

The deploy script will **fail fast** if `.env` is missing.

### 6. First boot

```bash
docker compose up -d --build
docker compose ps
```

Open `http://<SERVER_IP>:3119` and log in with `DEFAULT_ADMIN_EMAIL` /
`DEFAULT_ADMIN_PASSWORD`. Once this works, every later deploy will be fully automatic.

---

## Optional: GitHub Environment Protection

The workflow uses `environment: production`. To require manual approval:

1. **Settings → Environments → New environment** → name it `production`.
2. Enable **Required reviewers** and pick yourself.
3. From now on every deploy waits for your click before running.

---

## Deploy Flow on the Server

The `deploy` job runs this script over SSH:

1. `cd /home/<SERVER_USER>/arkon`
2. `git fetch --all --prune` + `git reset --hard origin/main` (clean sync)
3. Verify `.env` exists (fail fast otherwise)
4. `docker compose up -d --build --remove-orphans`
5. Poll `/health` for up to 2.5 min until the API is healthy
6. `docker image prune -f` to free disk
7. Print `docker compose ps` for confirmation

If health check fails the job exits **non-zero** and prints the last 100 lines
of the API logs so you can debug from the GitHub Actions UI.

---

## Troubleshooting

**`Permission denied (publickey)`**
→ The public key is not in `~/.ssh/authorized_keys` on the server, or the
  private key in `SERVER_KEY` doesn't match. Re-do step 3.

**`.env file is missing on server`**
→ SSH in and run `cp .env.example .env` then edit it.

**`docker: command not found`**
→ Docker is not installed or `SERVER_USER` is not in the `docker` group
  (re-login after `usermod -aG docker`).

**API never becomes healthy**
→ Check `docker compose logs api` on the server. Often a bad value in `.env`
  (DB URL, SECRET_KEY missing, etc.).

**Lint fails on existing code**
→ Run `ruff check app/ alembic/` and `cd frontend && npm run lint && npx tsc --noEmit`
  locally and fix issues before pushing.
