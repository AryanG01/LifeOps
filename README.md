# Clawdbot Life Ops + PVI

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://python.org)
[![Telegram Bot](https://img.shields.io/badge/Telegram-bot-26A5E4?logo=telegram)](https://core.telegram.org/bots)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker)](https://docs.docker.com/get-docker/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A personal ops bot that ingests Gmail and Canvas (NUS) updates, extracts action items, schedules reminders, and generates a daily digest adapted to your Personal Volatility Index (PVI).

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

## What it does

- **Unified inbox** — normalizes Gmail + Canvas notifications into a single feed
- **Smart task extraction** — LLM identifies action items, due dates, and reply drafts
- **Daily digest** — Markdown report sent to Telegram every morning at 7am
- **PVI engine** — scores your daily load and adapts notification intensity
- **Reminders** — scheduled based on due dates and PVI policy, pushed via Telegram

## Tech stack

Python 3.11 · FastAPI · PostgreSQL · Alembic · APScheduler · Typer · Telegram Bot API · Anthropic Claude

## Project structure

```
apps/
  api/          # FastAPI server (REST endpoints)
  worker/       # APScheduler background jobs
  web/          # Web dashboard (Phase 4 — placeholder)
packages/
  core/         # DB models, schemas, PVI engine, LLM extractor, config
  connectors/   # Gmail OAuth + polling, Canvas email-bridge parser
  cli/          # `claw` CLI
infra/
  docker-compose.yml
  alembic/      # Database migrations
tests/
  unit/
  integration/
```

## Quick start

**Prerequisites:** Docker, Python 3.11+, a Google Cloud OAuth credentials JSON, Anthropic API key

**1. Start Postgres**
```bash
docker-compose -f infra/docker-compose.yml up -d db
```

**2. Run migrations**
```bash
cd infra && alembic upgrade head
```

**3. Install packages (from repo root)**
```bash
pip install -e packages/core -e packages/connectors -e packages/cli
```

**4. Configure environment**
```bash
cp .env.example .env
# Edit .env — fill in ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
```

**5. Initialise and connect**
```bash
claw init
claw connect gmail    # opens browser OAuth flow
```

**6. Sync and view digest**
```bash
claw sync
claw digest today
```

## CLI reference

| Command | Description |
|---|---|
| `claw init` | Create default user in DB |
| `claw connect gmail` | Run Gmail OAuth flow |
| `claw sync` | Poll Gmail, normalise, extract |
| `claw inbox` | Show unified inbox |
| `claw inbox show <id>` | Full message detail + tasks |
| `claw inbox search "<q>"` | Search inbox |
| `claw tasks` | List all tasks |
| `claw tasks accept <id>` | Promote proposed → active |
| `claw tasks done <id>` | Mark task done |
| `claw tasks dismiss <id>` | Dismiss task |
| `claw snooze <id> <hours>` | Snooze next reminder |
| `claw digest today` | Print today's digest |
| `claw pvi today` | Print PVI score + policy |
| `claw replay extract` | Re-run LLM extraction |

## Roadmap

| Phase | Status | Scope |
|---|---|---|
| 1 — MVP | Done | Gmail + Canvas bridge, PVI, Telegram digest |
| 2 — Connectors + PVI v2 | Done | Outlook, GCal, Canvas API, LLM triage |
| 3 — Always-on bot | Done | Docker stack, Telegram bot, health alerts, error resilience |
| 4 — Web dashboard | Planned | FastAPI web UI, multi-user, analytics |

## Security

- Tokens stored in OS keychain (keyring), never in logs
- API server binds to localhost only
- No emails are sent automatically — drafts only
- Full privacy mode available: store only metadata/snippets, disable LLM
