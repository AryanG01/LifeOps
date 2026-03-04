# Clawdbot — Personal Ops Bot

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://python.org)
[![Telegram Bot](https://img.shields.io/badge/Telegram-bot-26A5E4?logo=telegram)](https://core.telegram.org/bots)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker)](https://docs.docker.com/get-docker/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Clawdbot reads your Gmail, Outlook, and NUS Canvas notifications, figures out what needs action, and keeps you on top of things via an interactive Telegram bot and a CLI. It runs forever on free-tier infrastructure ($0/month).

```
Email arrives → LLM triage → extract tasks + due dates → push to Telegram
                                                         ↓
                                             /tasks  /newtask  /digest  /pvi
```

---

## Features

### Implemented

| Feature | Description |
|---------|-------------|
| **Gmail sync** | History API delta polling — only fetches new messages since last sync |
| **Outlook / NUS Exchange** | Microsoft Graph delta endpoint, device-code OAuth |
| **Google Calendar** | 14-day event window, meeting prep 30 min before events |
| **Canvas (NUS)** | Extracts course code, assignment title, due date from Canvas notification emails |
| **LLM triage** | Fast cheap pre-filter (Gemini Flash Lite) before full extraction |
| **LLM extraction** | Pulls action items, urgency score, summary, reply drafts from emails |
| **Dual LLM providers** | Gemini 2.0 Flash (free, default) or Anthropic Claude — switchable via CLI |
| **Task management** | Auto-create from emails; accept / dismiss / done / snooze from Telegram or CLI |
| **Reminders** | Auto-scheduled from due dates, pushed to Telegram; silenced during focus sessions |
| **PVI engine** | Daily 0–100 Personal Velocity Index; adapts digest length and reminder cadence |
| **Daily digest** | Sent at 7am via Telegram — do-today tasks, upcoming, inbox summary, PVI score |
| **Weekly review** | 7-day PVI sparkline, task completion rate, overdue summary |
| **Focus / DND mode** | Silences reminders for a set duration; start via `/focus 30` or `claw focus start 30m` |
| **Email reply drafting** | LLM drafts replies; approve and send via Telegram button or `claw reply send` |
| **Telegram interactive bot** | `/tasks`, `/newtask` (conversational), `/inbox`, `/digest`, `/pvi`, `/focus`, `/status` |
| **Inline task actions** | Accept / Dismiss / Snooze / Done buttons directly on Telegram task cards |
| **Priority labels** | 🔴 High / 🟡 Medium / 🟢 Low on every task card |
| **Overdue indicator** | ⚠️ OVERDUE shown on past-due tasks |
| **Web dashboard** | FastAPI + HTMX — view inbox, tasks, PVI; accept/dismiss without Telegram |
| **TUI dashboard** | `claw dash` — terminal dashboard with inbox, tasks, reminders, PVI |
| **System health alerts** | Rate-limited Telegram alerts when jobs fail or the LLM circuit opens |
| **Circuit breaker** | LLM calls pause automatically after repeated failures; resume when service recovers |
| **Deduplication** | SHA-256 hash per message — same email never processed twice |
| **One-command setup** | `./setup.sh --wizard` — installs deps, fills .env interactively, runs migrations |
| **Docker Compose stack** | Full 5-service stack (db, migrate, api, worker, bot) |
| **Free cloud deploy** | GCP e2-micro + Neon.tech Postgres — $0/month forever |
| **Auto-update on VPS** | Cron `git pull + systemctl restart` every 10 minutes |

### Planned

| Feature | Description |
|---------|-------------|
| Slack / Discord integration | Push digest and tasks to Slack or Discord channels |
| iOS / Android push | Native mobile notifications via Pushover or Pushbullet |
| Voice digest | Text-to-speech audio digest sent as Telegram voice message |
| Linear / Jira sync | Two-way task sync with project management tools |
| AI scheduling | Suggest optimal time slots based on calendar + PVI |
| Multi-calendar | Support for multiple Google accounts |
| Attachment summarisation | Summarise PDF/DOCX attachments attached to emails |

---

## Prerequisites

Before you begin, collect these:

| Thing | Where to get it | Required? |
|-------|----------------|-----------|
| **Python 3.11+** | https://python.org | ✅ |
| **Gemini API key** | https://aistudio.google.com/app/apikey — free, 250 req/day | ✅ |
| **Telegram bot token** | Message `@BotFather` → `/newbot` | ✅ |
| **Telegram chat ID** | See step below | ✅ |
| **Gmail OAuth credentials JSON** | Google Cloud Console → APIs & Services → Credentials → OAuth 2.0 Client ID | ✅ |
| **Anthropic API key** | https://console.anthropic.com/ | Optional |
| **Outlook/NUS app client ID** | Azure Portal → App registrations | Optional |
| **Docker** | https://docs.docker.com/get-docker/ | For local/Docker deploy |

**Getting your Telegram chat ID:**
1. Start a chat with your bot (send any message)
2. Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
3. Copy the `"id"` value inside the `"chat"` object

**Gmail OAuth credentials JSON:**
1. Go to [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → Credentials
2. Create an OAuth 2.0 Client ID (Desktop app type)
3. Enable the Gmail API and Google Calendar API
4. Download the JSON → save as `~/.config/clawdbot/gmail_credentials.json`

---

## Setup

### Option 1: Local / Docker (recommended for development)

```bash
# Clone
git clone https://github.com/AryanG01/LifeOps.git
cd LifeOps

# One-command setup — installs packages, copies .env, starts Postgres, runs migrations
./setup.sh --wizard

# Connect accounts
claw connect gmail        # opens browser OAuth
claw connect gcal         # optional: Google Calendar
claw connect outlook      # optional: NUS/Outlook

# Start everything
cd infra && docker compose up -d
```

The Docker stack runs: Postgres → migrations → API server → worker → Telegram bot.

---

### Option 2: GCP e2-micro + Neon.tech (free forever, no Docker)

This is the recommended production setup. Total cost: **$0/month**.

- **GCP e2-micro** — always-free VM (us-central1 / us-east1 / us-west1 only), 614 MB RAM
- **Neon.tech** — serverless Postgres, free 500 MB

#### Step 1 — Create a Neon database

1. Sign up at https://neon.tech (free)
2. Create a project → copy the connection string (looks like `postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require`)

#### Step 2 — Create a GCP e2-micro VM

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → Compute Engine → VM instances
2. Click **Create Instance**:
   - Machine type: **e2-micro**
   - Region: **us-central1** (required for always-free)
   - Boot disk: **Standard persistent disk, 30 GB**
   - OS: Debian 12 (Bookworm)
   - Firewall: allow HTTP + HTTPS if you want the web dashboard exposed
3. Click Create, then open **SSH** in the browser

#### Step 3 — VM setup

```bash
# In the SSH window:
sudo apt update && sudo apt install -y python3 python3-pip python3-venv git libffi-dev

# Fix cffi (needed by Google OAuth cryptography library)
pip install --break-system-packages cffi cryptography

# Clone the repo (use a GitHub PAT for private repos)
git clone https://github.com/AryanG01/LifeOps.git
cd LifeOps

# Install packages
pip install --break-system-packages -e packages/core -e packages/connectors \
    -e packages/cli -e apps/worker -e apps/bot

# Copy and fill in .env
cp .env.example .env
python3 -c "
content = open('.env.example').read()
# Edit values below before pasting
open('.env','w').write(content)
"
# Then edit .env with your actual values:
nano .env
```

Key `.env` values to set:
```
DATABASE_URL=postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require
GEMINI_API_KEY=your_key
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
TELEGRAM_ENABLED=true
USER_DISPLAY_NAME=Your Name
USER_EMAIL=you@example.com
```

```bash
# Run migrations
cd infra && python3 -m alembic upgrade head && cd ..

# Create your user
claw init
```

#### Step 4 — Transfer Gmail credentials

Gmail OAuth must be done on a machine with a browser. On your **local machine**:

```bash
./setup.sh
claw connect gmail   # opens browser

# Export the token to a file
python3 -c "
import keyring, pathlib
token = keyring.get_password('clawdbot-gmail', 'token')
p = pathlib.Path.home() / '.config/clawdbot/gmail_token.json'
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(token)
print('Token written to', p)
"
```

Then copy the two files to the VM using base64 (works through browser SSH):
```bash
# On local machine — get base64 of each file:
base64 ~/.config/clawdbot/gmail_credentials.json
base64 ~/.config/clawdbot/gmail_token.json
```

```bash
# On VM — paste and decode:
mkdir -p ~/.config/clawdbot
python3 -c "
import base64, pathlib
data = '<paste base64 here>'
pathlib.Path('~/.config/clawdbot/gmail_credentials.json').expanduser().write_bytes(base64.b64decode(data))
"
# Repeat for gmail_token.json
```

#### Step 5 — Create systemd services

```bash
sudo tee /etc/systemd/system/clawdbot-worker.service << 'EOF'
[Unit]
Description=Clawdbot Worker
After=network.target
[Service]
User=<your_vm_username>
WorkingDirectory=/home/<your_vm_username>/LifeOps
EnvironmentFile=/home/<your_vm_username>/LifeOps/.env
ExecStart=python3 -m worker.main
Restart=always
RestartSec=10
[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/clawdbot-bot.service << 'EOF'
[Unit]
Description=Clawdbot Telegram Bot
After=network.target
[Service]
User=<your_vm_username>
WorkingDirectory=/home/<your_vm_username>/LifeOps
EnvironmentFile=/home/<your_vm_username>/LifeOps/.env
ExecStart=python3 -m bot.main
Restart=always
RestartSec=10
[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now clawdbot-worker clawdbot-bot
```

Set the `PYTHONPATH` in each service's `[Service]` block if needed:
```
Environment=PYTHONPATH=/home/<user>/LifeOps/packages/core/src:/home/<user>/LifeOps/packages/connectors/src:/home/<user>/LifeOps/packages/cli/src:/home/<user>/LifeOps/apps/bot/src:/home/<user>/LifeOps/apps/worker/src
```

#### Step 6 — Auto-update cron

```bash
crontab -e
# Add this line:
*/10 * * * * cd ~/LifeOps && git pull origin master --quiet && sudo systemctl restart clawdbot-bot clawdbot-worker
```

---

## Telegram Bot Commands

Once `claw bot start` (or the systemd service) is running, send these commands to your bot:

| Command | What it does |
|---------|-------------|
| `/tasks` | List open tasks with priority labels and inline action buttons |
| `/newtask` | Start a 2-step conversation to create a task (asks title, then due date) |
| `/newtask Buy milk by Friday 5pm` | One-liner — create task directly with parsed due date |
| `/inbox` | Show last 5 messages with summaries |
| `/digest` | Generate and send today's digest now |
| `/pvi` | Show today's PVI score with progress bar |
| `/focus 30` | Start a 30-minute focus session (reminders silenced) |
| `/status` | System health — DB, LLM circuit breaker, Telegram |
| `/cancel` | Cancel an in-progress `/newtask` conversation |

**Inline buttons on task cards:**
- ✓ Accept — move proposed → active
- ✗ Dismiss — remove from list
- ⏰ Snooze 2h — adds a reminder 2 hours from now
- ✅ Done — mark completed

---

## CLI Reference

Run all `claw` commands from the **project root**, not from `infra/`.

```bash
# Setup
claw init                        # create default user in DB
claw status                      # system health (DB, sources, LLM, Telegram)

# Connect accounts
claw connect gmail               # Gmail OAuth (opens browser)
claw connect gcal                # Google Calendar OAuth
claw connect outlook             # Outlook / NUS Exchange (device code flow)

# Daily use
claw today                       # morning briefing: calendar, tasks, PVI
claw sync                        # manually poll all sources now
claw dash                        # interactive TUI dashboard

# Inbox
claw inbox list                  # recent emails
claw inbox show <id>             # full message + extracted tasks
claw inbox search "<query>"      # search messages

# Tasks
claw tasks list                  # open tasks
claw tasks accept <id>           # proposed → active
claw tasks done <id>             # mark complete
claw tasks dismiss <id>          # dismiss
claw snooze <id> 2h              # snooze reminder by 2 hours

# Reminders
claw reminders list              # upcoming reminders

# Focus mode
claw focus start 90m             # focus for 90 minutes (silences reminders)
claw focus status                # check if focus is active
claw focus end                   # end focus early

# Email replies
claw reply list                  # emails with LLM-drafted replies
claw reply view <id>             # read the draft
claw reply send <id>             # send via Gmail

# Digest
claw digest today                # print today's digest
claw digest --weekly             # weekly review (7-day PVI trend)

# PVI
claw pvi today                   # PVI score and explanation

# LLM
claw llm status                  # show active provider + model
claw llm use gemini              # switch to Gemini
claw llm use anthropic           # switch to Anthropic Claude
claw llm test                    # send a test prompt

# Bot
claw bot start                   # start Telegram bot (foreground)

# Worker
claw worker start                # start background scheduler (foreground)
```

---

## Background Worker Jobs

The worker (`apps/worker`) runs these jobs automatically:

| Job | Frequency | What it does |
|-----|-----------|-------------|
| Poll Gmail | Every 2 min | Fetch new emails via History API |
| Poll Outlook | Every 2 min | Fetch new emails via Graph delta |
| Poll Google Calendar | Every 15 min | Sync events for next 14 days |
| LLM extraction | Every 5 min | Process new messages → tasks + reminders |
| Dispatch reminders | Every 1 min | Push due reminders to Telegram |
| Meeting prep | Every 5 min | 30-min pre-meeting briefing to Telegram |
| Daily digest | 7am daily | Generate PVI + digest, push to Telegram |
| System heartbeat | Every 5 min | Health check, alert on failures |

---

## PVI — Personal Velocity Index

A daily 0–100 score that reflects your current load and adapts the system's behaviour:

| Score | Regime | Effect |
|-------|--------|--------|
| 75–100 | Overloaded | Fewer digest items, gentler reminder cadence |
| 60–74 | Peak | Standard digest, standard reminders |
| 40–59 | Normal | Full digest, standard reminders |
| 0–39 | Recovery | Full digest, minimal reminders |

View with `/pvi` in Telegram or `claw pvi today` in the CLI.

---

## Project Structure

```
LifeOps/
├── packages/
│   ├── core/src/core/
│   │   ├── config.py            — Settings (get_settings singleton, reads .env)
│   │   ├── db/
│   │   │   ├── engine.py        — get_db() context manager (auto-commit)
│   │   │   └── models.py        — 16 ORM models
│   │   ├── digest/generator.py  — Daily digest builder
│   │   ├── pvi/calculator.py    — PVI scoring engine
│   │   ├── llm/extractor.py     — LLM extraction (Gemini / Anthropic)
│   │   ├── circuit_breaker.py   — Pause LLM calls after repeated failures
│   │   ├── health.py            — Rate-limited Telegram health alerts
│   │   ├── telegram_client.py   — httpx Telegram API client
│   │   └── telegram_notify.py   — Task push notifications with inline keyboard
│   ├── connectors/src/connectors/
│   │   ├── gmail/               — Gmail OAuth + History API poller
│   │   ├── outlook/             — MSAL device code + Graph delta poller
│   │   ├── gcal/                — Google Calendar 14-day poller
│   │   └── canvas/              — Canvas email parser (NUS-specific)
│   └── cli/src/cli/commands/    — All `claw` subcommands
├── apps/
│   ├── worker/src/worker/
│   │   ├── main.py              — APScheduler setup, 8 jobs registered
│   │   └── jobs.py              — Job implementations with circuit breaker
│   ├── bot/src/bot/
│   │   ├── main.py              — python-telegram-bot Application
│   │   ├── keyboards.py         — Inline keyboard builders
│   │   └── handlers/
│   │       ├── commands.py      — /tasks /newtask /inbox /digest /pvi /focus /status
│   │       └── callbacks.py     — accept / dismiss / done / snooze / reply_send
│   └── api/src/api/
│       ├── main.py              — FastAPI app + Jinja2 templates
│       ├── auth.py              — API key auth (disabled if key is empty)
│       └── routes/dashboard_api.py — REST endpoints for web dashboard
├── infra/
│   ├── docker-compose.yml       — 5 services: db, migrate, api, worker, bot
│   └── alembic/                 — Database migrations
├── tests/
│   ├── unit/                    — 135 unit tests (all green)
│   └── integration/
├── docs/
│   └── deployment.md            — Railway / Fly.io / VPS / GCP / Oracle deploy guides
├── setup.sh                     — One-command setup script
├── setup_wizard.py              — Interactive credential wizard
└── .env.example                 — All environment variables documented
```

---

## Environment Variables

See `.env.example` for the full list with comments. Key variables:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | Postgres connection string |
| `GEMINI_API_KEY` | Gemini API key (free tier sufficient) |
| `LLM_PROVIDER` | `gemini` (default) or `anthropic` |
| `TELEGRAM_BOT_TOKEN` | From @BotFather |
| `TELEGRAM_CHAT_ID` | Your personal chat ID |
| `TELEGRAM_ENABLED` | Set `true` to enable Telegram push |
| `GMAIL_CREDENTIALS_PATH` | Path to OAuth client secrets JSON |
| `OUTLOOK_CLIENT_ID` | Azure app registration ID |
| `OUTLOOK_TENANT` | `organizations` for NUS, `common` for personal |
| `USER_EMAIL` | Your email — used by `claw init` |
| `USER_TIMEZONE` | e.g. `Asia/Singapore` |
| `BOT_NOTIFY_MIN_PRIORITY` | Min priority (0–100) for immediate Telegram push. Default: 60 |
| `DASHBOARD_API_KEY` | Web dashboard API key (leave blank to disable auth in dev) |

---

## Running Tests

```bash
# From project root
PYTHONPATH=packages/core/src:packages/connectors/src:packages/cli/src:apps/bot/src \
    python3 -m pytest tests/unit/ -v
```

135 tests, all green.

---

## Web Dashboard

Available at `http://localhost:8000` when the API server is running.

Pages:
- `/` — overview dashboard (inbox summary, open tasks, PVI)
- `/tasks` — full task list with accept / dismiss buttons
- `/inbox` — recent messages
- `/api/tasks` — JSON API
- `/api/pvi/today` — today's PVI as JSON

Protected by `DASHBOARD_API_KEY` (set in `.env`). Leave blank to disable auth during local development.

---

## Security

- OAuth tokens stored in OS keychain (`keyring`) or `~/.config/clawdbot/tokens/` (headless fallback) — never in logs or DB
- All bot commands guarded by `TELEGRAM_CHAT_ID` — only your chat can control the bot
- API server binds to `127.0.0.1` by default (change to `0.0.0.0` for Docker/VPS)
- Emails never sent automatically — LLM-drafted replies require explicit approval
- LLM circuit breaker prevents cascading failures from upstream API outages
- `credentials/` and `.env` are gitignored

---

## Deployment Options

Full guide: [docs/deployment.md](docs/deployment.md)

| Option | Cost | Effort | Best for |
|--------|------|--------|----------|
| GCP e2-micro + Neon.tech | **$0/month** | Medium | Personal, permanent |
| Railway | ~$5/month | Easy | Quick deploy |
| Fly.io | ~$3/month | Easy | Quick deploy |
| Self-hosted VPS | ~$5/month | Medium | Full control |
| Oracle Cloud Free Tier | **$0/month** | Medium | More RAM (24 GB) |
| Local Docker | $0 | Easy | Development |
