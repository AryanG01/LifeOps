# T2: Docker Compose Full Stack — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** `docker compose up -d` (from `infra/`) starts DB + migrations + worker + API + bot — all wired with `env_file`, proper dependency ordering, and `restart: unless-stopped`.

**Architecture:** Extend existing `infra/docker-compose.yml` (which already has db/api/worker) with: a `migrate` one-shot service, a `bot` service, `env_file: ../.env` on all services, `restart: unless-stopped` on long-running services, and proper `depends_on` chains. Add `apps/bot/Dockerfile` mirroring the worker pattern.

**Tech Stack:** Docker Compose v3.9, Python 3.11-slim base image, Alembic migrations.

**No tests** — verified by running `docker compose config` (validates YAML) and confirming all referenced Dockerfiles exist.

---

## Task 1: Create `apps/bot/Dockerfile`

**Files:**
- Create: `apps/bot/Dockerfile`

**Step 1: Check the worker Dockerfile for the pattern**

Read `/Users/aryanganju/Desktop/Code/LifeOps/apps/worker/Dockerfile` — it copies `packages/core`, `packages/connectors`, and `apps/worker`, installs editable, then runs `python -m worker.main`.

**Step 2: Create bot Dockerfile**

Create `apps/bot/Dockerfile`:

```dockerfile
FROM python:3.11-slim
WORKDIR /app

COPY packages/core packages/core
COPY packages/connectors packages/connectors
COPY packages/cli packages/cli
COPY apps/bot apps/bot

RUN pip install --no-cache-dir \
    -e packages/core \
    -e packages/connectors \
    -e packages/cli \
    -e apps/bot

CMD ["python", "-m", "bot.main"]
```

**Step 3: Verify bot entry point exists**

Check that `apps/bot/src/bot/main.py` has a `run()` function callable from `__main__`. Create/update `apps/bot/src/bot/__main__.py` if needed:

```python
from bot.main import run
run()
```

Check if `__main__.py` exists:
```bash
ls /Users/aryanganju/Desktop/Code/LifeOps/apps/bot/src/bot/__main__.py
```

If it doesn't exist, create it with:
```python
from bot.main import run
run()
```

**Step 4: Commit**

```bash
cd /Users/aryanganju/Desktop/Code/LifeOps
git add apps/bot/Dockerfile apps/bot/src/bot/__main__.py
git commit -m "feat(docker): add bot Dockerfile and __main__ entry point"
```

---

## Task 2: Update `infra/docker-compose.yml`

**Files:**
- Modify: `infra/docker-compose.yml`

**Step 1: Read current docker-compose.yml**

Read `/Users/aryanganju/Desktop/Code/LifeOps/infra/docker-compose.yml` to understand the current state before modifying.

**Step 2: Replace with updated version**

The new `infra/docker-compose.yml`:

```yaml
version: "3.9"
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: clawdbot
      POSTGRES_PASSWORD: clawdbot
      POSTGRES_DB: clawdbot
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U clawdbot"]
      interval: 5s
      timeout: 5s
      retries: 5

  migrate:
    build:
      context: ..
      dockerfile: infra/Dockerfile.migrate
    command: ["python", "-m", "alembic", "-c", "infra/alembic.ini", "upgrade", "head"]
    env_file: ../.env
    environment:
      DATABASE_URL: postgresql://clawdbot:clawdbot@db:5432/clawdbot
    depends_on:
      db:
        condition: service_healthy

  api:
    build:
      context: ..
      dockerfile: apps/api/Dockerfile
    env_file: ../.env
    environment:
      DATABASE_URL: postgresql://clawdbot:clawdbot@db:5432/clawdbot
    ports:
      - "127.0.0.1:8000:8000"
    depends_on:
      migrate:
        condition: service_completed_successfully
    restart: unless-stopped

  worker:
    build:
      context: ..
      dockerfile: apps/worker/Dockerfile
    env_file: ../.env
    environment:
      DATABASE_URL: postgresql://clawdbot:clawdbot@db:5432/clawdbot
    depends_on:
      migrate:
        condition: service_completed_successfully
    restart: unless-stopped

  bot:
    build:
      context: ..
      dockerfile: apps/bot/Dockerfile
    env_file: ../.env
    environment:
      DATABASE_URL: postgresql://clawdbot:clawdbot@db:5432/clawdbot
    depends_on:
      migrate:
        condition: service_completed_successfully
    restart: unless-stopped

volumes:
  pgdata:
```

**Step 3: Create `infra/Dockerfile.migrate`**

The migrate service needs a minimal image with alembic + core packages. Create `infra/Dockerfile.migrate`:

```dockerfile
FROM python:3.11-slim
WORKDIR /app

COPY packages/core packages/core
COPY packages/connectors packages/connectors
COPY infra infra

RUN pip install --no-cache-dir \
    -e packages/core \
    -e packages/connectors \
    alembic psycopg2-binary

WORKDIR /app/infra
```

**Step 4: Validate the compose file**

```bash
cd /Users/aryanganju/Desktop/Code/LifeOps/infra
docker compose config 2>&1 | head -20
```

Expected: YAML output with all 6 services (db, migrate, api, worker, bot) — no errors.

If `docker` is not available, skip this and just verify YAML is valid:
```bash
python3 -c "import yaml; yaml.safe_load(open('docker-compose.yml'))" && echo "YAML valid"
```

**Step 5: Update phase3 tracker**

In `docs/plans/2026-03-02-clawdbot-phase3.md`, mark T2 done:
```
- [x] Task 2: Docker Compose full stack (worker + API + DB + migrations auto-run) ✅ DONE
```

**Step 6: Commit**

```bash
cd /Users/aryanganju/Desktop/Code/LifeOps
git add infra/docker-compose.yml infra/Dockerfile.migrate \
        docs/plans/2026-03-02-clawdbot-phase3.md
git commit -m "feat(docker): full compose stack with migrate + bot + env_file + restart"
```
