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

Railway reads `.railway.json` (see railway.toml in repo root). Each service is a separate Railway service:

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
    --region sin \
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

The `fly.toml` mounts this at `/root/.config/clawdbot`.

### Step 5: Run migrations

```bash
fly ssh console -C "cd /app && python3 -m alembic -c infra/alembic.ini upgrade head"
# or use the [deploy] release_command in fly.toml
```

### Step 6: Deploy

```bash
fly deploy
```

**Check logs:**
```bash
fly logs
```

**Redeploy after code changes:**
```bash
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

The `docker-compose.yml` mounts `/root/.config/clawdbot` into the worker and bot containers.

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

```bash
systemctl enable docker   # already done in Step 1
```

For an additional safety net:

```bash
# crontab -e
@reboot sleep 30 && cd /root/LifeOps/infra && docker compose up -d
```

### Step 7: (Optional) Web dashboard access via Cloudflare Tunnel

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
docker compose up -d --no-deps worker bot
```

### New migrations

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
