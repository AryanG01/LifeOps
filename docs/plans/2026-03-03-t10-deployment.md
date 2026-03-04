# T10: Deployment Guide — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Anyone can deploy Clawdbot to a VPS or cloud platform in under 30 minutes using a clear, step-by-step guide.

**Architecture:** Four deployment targets are documented — Railway (easiest, auto-deploys from git), Fly.io (cheap persistent VPS with named processes), self-hosted VPS with Docker Compose (most control), and local-only with Docker Compose (for dev). Gmail OAuth credentials (stored on-disk as `gmail_credentials.json`) cannot be generated inside a container, so the guide explains how to generate them locally first and then mount the file as a Docker volume or upload it as a secret. Config files `fly.toml` and `.railway.json` are committed to the repo so deploying is a single command after setup.

**Tech Stack:** bash, Docker Compose v3.9, fly CLI, railway CLI, TOML, JSON

**Test command:** `PYTHONPATH=packages/core/src:packages/connectors/src:packages/cli/src python3 -m pytest tests/unit/ -v`

---

## Task 1: Create `docs/deployment.md` — comprehensive deployment guide

**Files:**
- Create: `docs/deployment.md`

**Step 1: Check what already exists in `docs/`**

```bash
ls /Users/aryanganju/Desktop/Code/LifeOps/docs/
```

Also read `infra/docker-compose.yml` to confirm the current service list (db, migrate, api, worker, bot):

```bash
cat /Users/aryanganju/Desktop/Code/LifeOps/infra/docker-compose.yml
```

**Step 2: Create `docs/deployment.md`**

Write `/Users/aryanganju/Desktop/Code/LifeOps/docs/deployment.md`:

```markdown
# Clawdbot — Deployment Guide

> **Time to deploy:** 15–30 minutes depending on option chosen.

Clawdbot runs as three long-lived services:

| Service | Purpose |
|---------|---------|
| `db` | PostgreSQL 16 — stores all messages, tasks, PVI state |
| `worker` | APScheduler — polls Gmail/Outlook, runs LLM extraction, sends reminders |
| `bot` | python-telegram-bot — handles Telegram commands and inline buttons |

A fourth ephemeral service (`migrate`) runs Alembic migrations on startup and exits.

---

## Prerequisites (all options)

Before deploying you need:

1. **Gmail credentials JSON** — follow steps in [Gmail OAuth setup](#gmail-oauth-setup)
2. **`.env` file** — all variables filled in (run `./setup.sh --wizard` locally)
3. **Docker 24+** — for local/VPS options
4. A **Telegram bot token + chat ID** — see `.env.example`
5. A **Gemini API key** — https://aistudio.google.com/app/apikey (free)

---

## Gmail OAuth Setup

Gmail OAuth tokens **cannot** be generated inside a Docker container because they require a browser. Generate the token locally, then copy it into your deployment.

```bash
# 1. On your local machine:
./setup.sh                   # installs packages
claw connect gmail           # opens browser, saves token to OS keychain

# 2. Export the token to a file:
python3 -c "
import keyring, json, pathlib
token_json = keyring.get_password('clawdbot-gmail', 'token')
path = pathlib.Path.home() / '.config/clawdbot/gmail_token.json'
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(token_json)
print(f'Token written to {path}')
"

# You now have ~/.config/clawdbot/gmail_token.json
# This file is mounted into the worker/bot containers (see each option below).
```

> **Security:** Never commit `gmail_token.json` to git. It is already in `.gitignore`.

---

## Option A: Railway (Easiest — ~$5/mo)

Railway auto-deploys from git push, provides managed Postgres, and handles environment variables via its dashboard.

**Limitations:** Railway does not support Docker Compose natively — each service is deployed as a separate service pointing to its own Dockerfile. The `migrate` service must be run as a release command.

### Step 1: Install Railway CLI

```bash
npm i -g @railway/cli
# or: brew install railway
railway login
```

### Step 2: Create project + database

```bash
cd /path/to/LifeOps
railway init                          # creates a new Railway project
railway add --database postgresql     # provisions Postgres, injects DATABASE_URL
```

### Step 3: Set environment variables

In the Railway dashboard (https://railway.app → your project → Variables), add every key from your `.env`:

```
GEMINI_API_KEY=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
TELEGRAM_ENABLED=true
BOT_NOTIFY_MIN_PRIORITY=60
USER_TIMEZONE=Asia/Singapore
# DATABASE_URL is injected automatically by Railway
```

### Step 4: Upload Gmail token as a volume-like env var

Railway does not support volumes, so encode the token as base64 and decode it at startup.

```bash
# Local: encode the token
TOKEN_B64=$(base64 -i ~/.config/clawdbot/gmail_token.json)
# Paste $TOKEN_B64 into Railway Variables as: GMAIL_TOKEN_B64=...
```

Add a startup hook in `apps/worker/src/worker/main.py` to decode it:

```python
import os, base64, pathlib
_b64 = os.getenv("GMAIL_TOKEN_B64")
if _b64:
    p = pathlib.Path.home() / ".config/clawdbot/gmail_token.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(base64.b64decode(_b64))
```

### Step 5: Configure services

Railway reads `.railway.json` (created in Task 4 below). Each service is a separate Railway service:

- **migrate** — runs once on deploy (release command)
- **worker** — persistent process
- **bot** — persistent process

### Step 6: Deploy

```bash
railway up
```

Railway builds each Dockerfile, runs the release command (migrations), then starts worker + bot.

**Redeploy after code changes:**
```bash
git push origin master    # Railway auto-deploys on push if GitHub is linked
# or:
railway up
```

---

## Option B: Fly.io (~$3–5/mo)

Fly.io runs Docker containers on shared VMs. With `[processes]` in `fly.toml` you can run worker + bot as separate processes in one app, sharing the same image.

### Step 1: Install flyctl

```bash
brew install flyctl
# or: curl -L https://fly.io/install.sh | sh
fly auth login
```

### Step 2: Create app + Postgres

```bash
cd /path/to/LifeOps
fly launch --no-deploy          # creates fly.toml (or use the one in this repo)
fly postgres create \
    --name clawdbot-db \
    --region sin \              # Singapore — change to your nearest region
    --vm-size shared-cpu-1x \
    --volume-size 3
fly postgres attach clawdbot-db # injects DATABASE_URL as a secret
```

### Step 3: Set secrets

```bash
fly secrets set \
  GEMINI_API_KEY="..." \
  TELEGRAM_BOT_TOKEN="..." \
  TELEGRAM_CHAT_ID="..." \
  TELEGRAM_ENABLED="true" \
  BOT_NOTIFY_MIN_PRIORITY="60" \
  USER_TIMEZONE="Asia/Singapore"

# Upload Gmail token:
fly secrets set GMAIL_TOKEN_B64="$(base64 -i ~/.config/clawdbot/gmail_token.json)"
```

### Step 4: Create a volume for credentials

```bash
fly volumes create clawdbot_config --size 1 --region sin
```

The `fly.toml` (created in Task 3 below) mounts this at `/root/.config/clawdbot`.

### Step 5: Run migrations

```bash
fly ssh console -C "cd /app && python3 -m alembic -c infra/alembic.ini upgrade head"
# or use the [deploy] release_command in fly.toml (see Task 3)
```

### Step 6: Deploy

```bash
fly deploy
```

**Check logs:**
```bash
fly logs                        # all services
fly logs --app clawdbot-worker  # worker only (if named separately)
```

**Redeploy after code changes:**
```bash
git push origin master    # if GitHub Actions / Fly CD is configured
# or:
fly deploy
```

---

## Option C: Self-Hosted VPS (Most Control)

Recommended for: DigitalOcean Droplet ($4/mo), Hetzner Cloud (EUR 3.79/mo), or any Linux VPS.

### Step 1: Provision VPS

Minimum specs: 1 vCPU, 1 GB RAM, 10 GB SSD. Ubuntu 22.04 LTS recommended.

```bash
# On your VPS:
apt update && apt install -y git docker.io docker-compose-plugin python3.11 python3-pip
systemctl enable docker && systemctl start docker
```

### Step 2: Clone and configure

```bash
git clone https://github.com/AryanG01/LifeOps.git
cd LifeOps
cp .env.example .env
nano .env     # fill in all credentials
```

### Step 3: Upload Gmail credentials

```bash
# From your local machine:
scp ~/.config/clawdbot/gmail_token.json user@your-vps:/root/.config/clawdbot/gmail_token.json
scp ~/.config/clawdbot/gmail_credentials.json user@your-vps:/root/.config/clawdbot/gmail_credentials.json
```

The `docker-compose.yml` mounts `/root/.config/clawdbot` into the worker and bot containers:

```yaml
volumes:
  - /root/.config/clawdbot:/root/.config/clawdbot
```

### Step 4: Start everything

```bash
cd infra
docker compose up -d
```

This starts: db → migrate (one-shot) → worker + bot (restart: unless-stopped).

### Step 5: Verify

```bash
docker compose ps          # all services should show "running" (except migrate = "exited 0")
docker compose logs worker  # check for "scheduler started" and first poll logs
docker compose logs bot     # check for "bot polling started"
```

### Step 6: Enable auto-restart on reboot

Docker Compose services already have `restart: unless-stopped`. The Docker daemon itself should be enabled:

```bash
systemctl enable docker   # already done in Step 1
```

For an additional safety net, add a cron job that ensures the stack is up:

```bash
# crontab -e
@reboot sleep 30 && cd /root/LifeOps/infra && docker compose up -d
```

### Step 7: (Optional) Web dashboard access via Cloudflare Tunnel

To access the FastAPI dashboard (`localhost:8000`) from anywhere without opening firewall ports:

```bash
# On VPS:
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
    -o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared
cloudflared tunnel login
cloudflared tunnel create clawdbot
cloudflared tunnel route dns clawdbot clawdbot.yourdomain.com
cloudflared tunnel run clawdbot
```

---

## Updating Clawdbot

### Self-hosted VPS

```bash
cd /root/LifeOps
git pull origin master
cd infra
docker compose build worker bot
docker compose up -d --no-deps worker bot   # rolling restart, DB untouched
```

### New migrations (run after `git pull` if `infra/alembic/versions/` has new files)

```bash
cd infra
docker compose run --rm migrate
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `worker` exits immediately | Missing env var | `docker compose logs worker` — look for `ValidationError` or `KeyError` |
| Gmail not polling | Token expired | Re-run `claw connect gmail` locally, re-upload token |
| Telegram not sending | `TELEGRAM_ENABLED=false` | Set `TELEGRAM_ENABLED=true` in `.env` / secrets |
| `migrate` exits non-zero | DB not ready | Check `docker compose logs db` — wait for "ready to accept connections" |
| `AADSTS50059` (Outlook) | Wrong tenant | Set `OUTLOOK_TENANT=organizations` in `.env` |
| LLM extraction failing | API key invalid or quota exceeded | Check `GEMINI_API_KEY`, visit https://aistudio.google.com |

---

## Cost Summary

| Platform | DB | Compute | Est. monthly |
|----------|----|---------|-------------|
| Railway | Managed Postgres $5 | Worker+Bot ~$0–2 | ~$5–7 |
| Fly.io | Postgres shared $0–3 | 2 processes shared VM ~$2 | ~$3–5 |
| DigitalOcean Droplet | Docker on VPS | $4/mo Droplet | ~$4 |
| Hetzner Cloud | Docker on VPS | CX11 EUR 3.79/mo | ~$4 |
| Local Mac | Existing machine | Free | $0 |
```

**Step 3: Verify the Markdown is well-formed**

```bash
python3 -c "
import pathlib
text = pathlib.Path('/Users/aryanganju/Desktop/Code/LifeOps/docs/deployment.md').read_text()
# Count headings and tables as a basic sanity check
headings = [l for l in text.splitlines() if l.startswith('#')]
print(f'Headings: {len(headings)}')
print(f'Total lines: {len(text.splitlines())}')
print('OK')
"
```

Expected: prints heading count and total lines, `OK`.

**Step 4: Commit**

```bash
cd /Users/aryanganju/Desktop/Code/LifeOps
git add docs/deployment.md
git commit -m "docs(deploy): add comprehensive deployment guide (Railway/Fly.io/VPS)"
```

---

## Task 2: Update `README.md` — add Quick Deploy section + badges

**Files:**
- Modify: `README.md`

**Step 1: Read current README**

Read `/Users/aryanganju/Desktop/Code/LifeOps/README.md` to understand the current structure. Note the first line (title) and the "Quick start" section.

**Step 2: Add badges after the title line**

The current README starts with `# Clawdbot Life Ops + PVI`. Insert badges on the line immediately after the title:

```markdown
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://python.org)
[![Telegram Bot](https://img.shields.io/badge/Telegram-bot-26A5E4?logo=telegram)](https://core.telegram.org/bots)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker)](https://docs.docker.com/get-docker/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
```

**Step 3: Add Quick Deploy section before "What it does"**

Insert the following block immediately after the badges and before the `## What it does` heading:

```markdown
## Quick Deploy

> **Get Clawdbot running in 15–30 minutes.** Full guide: [docs/deployment.md](docs/deployment.md)

```bash
# 1. Clone and run one-command setup:
git clone https://github.com/AryanG01/LifeOps.git && cd LifeOps
./setup.sh --wizard          # installs deps, fills in .env interactively

# 2. Connect your accounts:
claw connect gmail            # Gmail OAuth (opens browser)
claw connect gcal             # optional: Google Calendar
claw connect outlook          # optional: NUS/Outlook

# 3. Start the stack:
cd infra && docker compose up -d
```

**Deployment options:**
- **Railway** (easiest): `railway login && railway up` — see [Railway deploy](docs/deployment.md#option-a-railway-easiest----5mo)
- **Fly.io**: `fly launch && fly deploy` — see [Fly.io deploy](docs/deployment.md#option-b-flyio-35mo)
- **VPS**: `git clone → ./setup.sh → docker compose up -d` — see [VPS deploy](docs/deployment.md#option-c-self-hosted-vps-most-control)
```

**Step 4: Update the Roadmap table to reflect Phase 3 completion**

Find the `## Roadmap` section and update the table rows to show current status:

```markdown
| Phase | Status | Scope |
|---|---|---|
| 1 — MVP | Done | Gmail + Canvas bridge, PVI, Telegram digest |
| 2 — Connectors + PVI v2 | Done | Outlook, GCal, Canvas API, LLM triage |
| 3 — Always-on bot | Done | Docker stack, Telegram bot, health alerts, error resilience |
| 4 — Web dashboard | Planned | FastAPI web UI, multi-user, analytics |
```

**Step 5: Run a quick line-count sanity check**

```bash
wc -l /Users/aryanganju/Desktop/Code/LifeOps/README.md
```

Expected: more lines than before (was ~107).

**Step 6: Commit**

```bash
cd /Users/aryanganju/Desktop/Code/LifeOps
git add README.md
git commit -m "docs(readme): add Quick Deploy section, badges, and updated roadmap"
```

---

## Task 3: Create `fly.toml`

**Files:**
- Create: `fly.toml`

**Step 1: Check if `fly.toml` already exists**

```bash
ls /Users/aryanganju/Desktop/Code/LifeOps/fly.toml 2>/dev/null && echo "exists" || echo "not found"
```

**Step 2: Create `fly.toml`**

Write `/Users/aryanganju/Desktop/Code/LifeOps/fly.toml`:

```toml
# Clawdbot — Fly.io configuration
# Deploy: fly deploy
# Docs: https://fly.io/docs/reference/configuration/

app = "clawdbot"
primary_region = "sin"   # Singapore — change to nearest: iad (US East), lhr (London), etc.

[build]
  # Build the worker Dockerfile from the project root
  dockerfile = "apps/worker/Dockerfile"

# Run two named processes from the same image.
# Fly creates a separate machine for each process group.
[processes]
  worker = "python -m worker.main"
  bot    = "python -m bot.main"

# Release command: run migrations before the new version goes live.
# Fly runs this in a temporary machine and only proceeds if exit code = 0.
[deploy]
  release_command = "python -m alembic -c infra/alembic.ini upgrade head"

# Worker process: no public port needed (outbound-only)
[[services]]
  processes = ["worker"]
  internal_port = 8001
  protocol = "tcp"

  [[services.tcp_checks]]
    interval = "30s"
    timeout  = "5s"

# Bot process: no public port needed (long-polling outbound)
[[services]]
  processes = ["bot"]
  internal_port = 8002
  protocol = "tcp"

  [[services.tcp_checks]]
    interval = "30s"
    timeout  = "5s"

# Persistent volume for Gmail OAuth token + credentials
[mounts]
  source      = "clawdbot_config"
  destination = "/root/.config/clawdbot"
  processes   = ["worker", "bot"]

# VM sizing — shared-cpu-1x (256 MB RAM) is enough for worker + bot
[[vm]]
  cpu_kind  = "shared"
  cpus      = 1
  memory_mb = 512

# Environment variables (non-secret defaults only — secrets go via `fly secrets set`)
[env]
  API_HOST       = "0.0.0.0"
  API_PORT       = "8000"
  LLM_PROVIDER   = "gemini"
  LLM_MODE       = "enabled"
  TELEGRAM_ENABLED = "true"
```

**Step 3: Validate TOML syntax**

```bash
python3 -c "
import tomllib, pathlib
data = tomllib.loads(pathlib.Path('/Users/aryanganju/Desktop/Code/LifeOps/fly.toml').read_text())
print('fly.toml: TOML valid')
print(f'  app = {data[\"app\"]}')
print(f'  primary_region = {data[\"primary_region\"]}')
print(f'  processes = {list(data[\"processes\"].keys())}')
"
```

Expected:
```
fly.toml: TOML valid
  app = clawdbot
  primary_region = sin
  processes = ['worker', 'bot']
```

**Step 4: Commit**

```bash
cd /Users/aryanganju/Desktop/Code/LifeOps
git add fly.toml
git commit -m "feat(deploy): add fly.toml for Fly.io deployment (worker + bot processes)"
```

---

## Task 4: Create `.railway.json`

**Files:**
- Create: `.railway.json`

**Step 1: Check if it already exists**

```bash
ls /Users/aryanganju/Desktop/Code/LifeOps/.railway.json 2>/dev/null && echo "exists" || echo "not found"
```

**Step 2: Research Railway config format**

Railway v3 uses a `railway.toml` or `.railway.json` file. The most portable format is `railway.toml` (supported since Railway CLI v3). Use `railway.toml` to avoid ambiguity with hidden dot-files.

**Step 3: Create `railway.toml`**

Write `/Users/aryanganju/Desktop/Code/LifeOps/railway.toml`:

```toml
# Clawdbot — Railway configuration
# Deploy: railway up
# Docs: https://docs.railway.app/reference/config-as-code

[build]
  builder = "DOCKERFILE"

# ---- Worker service --------------------------------------------------------
# In Railway, create a second service manually for the bot (Railway does not
# natively support multi-process in a single service). Point the bot service
# to the same repo with startCommand = "python -m bot.main".

[deploy]
  startCommand   = "python -m worker.main"
  restartPolicyType = "ON_FAILURE"
  restartPolicyMaxRetries = 5

  # Run migrations as a pre-deploy command.
  # Railway executes this before starting the main process on each deploy.
  # NOTE: Railway calls this the "pre-deploy command". Set it in the Railway
  # dashboard under Service → Settings → Deploy → Pre-deploy command:
  #   python -m alembic -c infra/alembic.ini upgrade head

# ---- Health check ----------------------------------------------------------
# Railway uses HTTP health checks. The worker exposes no HTTP port by default,
# so disable the health check here; Railway will use the process restart policy.

[healthcheck]
  disabled = true
```

**Step 4: Also create `.railway.json` for older Railway CLI compatibility**

Write `/Users/aryanganju/Desktop/Code/LifeOps/.railway.json`:

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "DOCKERFILE",
    "dockerfilePath": "apps/worker/Dockerfile"
  },
  "deploy": {
    "startCommand": "python -m worker.main",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 5
  }
}
```

**Step 5: Validate JSON syntax**

```bash
python3 -c "
import json, pathlib
data = json.loads(pathlib.Path('/Users/aryanganju/Desktop/Code/LifeOps/.railway.json').read_text())
print('.railway.json: JSON valid')
print(f'  builder = {data[\"build\"][\"builder\"]}')
print(f'  startCommand = {data[\"deploy\"][\"startCommand\"]}')
"
```

Expected:
```
.railway.json: JSON valid
  builder = DOCKERFILE
  startCommand = python -m worker.main
```

**Step 6: Validate `railway.toml` TOML syntax**

```bash
python3 -c "
import tomllib, pathlib
data = tomllib.loads(pathlib.Path('/Users/aryanganju/Desktop/Code/LifeOps/railway.toml').read_text())
print('railway.toml: TOML valid')
print(f'  startCommand = {data[\"deploy\"][\"startCommand\"]}')
"
```

Expected:
```
railway.toml: TOML valid
  startCommand = python -m worker.main
```

**Step 7: Update phase3 tracker**

In `docs/plans/2026-03-02-clawdbot-phase3.md`, mark T10 done:

```
- [x] Task 10: Deployment guide (Railway / Fly.io / self-hosted VPS) ✅ DONE
```

**Step 8: Commit**

```bash
cd /Users/aryanganju/Desktop/Code/LifeOps
git add railway.toml .railway.json docs/plans/2026-03-02-clawdbot-phase3.md
git commit -m "feat(deploy): add railway.toml + .railway.json for Railway deployment"
```

---

## Summary

| Task | File(s) | Verification |
|------|---------|-------------|
| 1 | `docs/deployment.md` | `python3 -c "..."` line count check |
| 2 | `README.md` | visual review; `wc -l README.md` |
| 3 | `fly.toml` | `python3 -c "import tomllib..."` |
| 4 | `railway.toml`, `.railway.json` | `python3 -c "import tomllib/json..."` |

No unit tests are written for these config files — correctness is verified by TOML/JSON parser validation. The actual deployment correctness is verified by a manual smoke-test deploy (optional) as described in `docs/deployment.md`.
