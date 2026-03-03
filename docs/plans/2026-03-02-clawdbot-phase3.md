# Clawdbot Phase 3 — From Terminal Tool to Always-On Personal OS

> **Vision:** Anyone can clone the repo, run one command, and get a fully working personal assistant — no terminal required day-to-day. Everything flows through Telegram (or a web app). The system runs forever, handles its own errors, and tells you when it needs attention.

---

## PROGRESS TRACKER

- [ ] Task 1: One-command setup (`setup.sh` + interactive wizard)
- [ ] Task 2: Docker Compose full stack (worker + API + DB + migrations auto-run)
- [x] Task 3: Telegram interactive bot — inline keyboards for task approval/dismissal ✅ DONE
- [ ] Task 4: Telegram email reply workflow — full thread → LLM draft → approve → send
- [x] Task 5: Telegram Canvas/assignment notifications (push when new deadline detected) ✅ DONE
- [x] Task 6: System health alerts via Telegram (LLM credits, Gmail auth expiry, errors) ✅ DONE
- [x] Task 7: Error resilience — circuit breakers, graceful degradation, no crash loops ✅ DONE
- [ ] Task 8: Multi-user support — each user has their own config/credentials
- [ ] Task 9: Web dashboard (FastAPI + lightweight frontend)
- [ ] Task 10: Deployment guide (Railway / Fly.io / self-hosted VPS)

---

## Architecture After Phase 3

```
┌─────────────────────────────────────────────────┐
│                   Sources                        │
│  Gmail · Outlook/NUS · Google Calendar · Canvas  │
└───────────────┬─────────────────────────────────┘
                │ delta poll (2 min)
                ▼
┌───────────────────────────────┐
│         Worker (APScheduler)  │
│  poll → normalize → triage    │
│  → LLM extract → tasks        │
│  → reminders → meeting prep   │
└────┬──────────────────────────┘
     │                    │
     ▼                    ▼
┌──────────┐      ┌────────────────────┐
│ Postgres │      │   Telegram Bot     │
│          │      │  (interactive)     │
│ raw      │      │  • task approval   │
│ messages │      │  • reply drafting  │
│ tasks    │      │  • daily digest    │
│ PVI      │      │  • system alerts   │
│ calendar │      │  • Canvas push     │
└──────────┘      └────────────────────┘
     │                    │
     ▼                    ▼
┌──────────────────────────────┐
│      FastAPI (localhost/VPS) │
│      Web dashboard (future)  │
└──────────────────────────────┘
```

---

## Task 1: One-Command Setup

**Goal:** `git clone → ./setup.sh → done`. Works for non-technical users.

**Files:**
- Create: `setup.sh`
- Create: `setup_wizard.py` (interactive prompts for all credentials)
- Create: `.env.example` (template with all vars documented)

**What `setup.sh` does:**
```bash
#!/bin/bash
# 1. Check Python 3.11+, Docker, pip
# 2. pip install -e packages/core packages/connectors packages/cli apps/worker
# 3. Copy .env.example → .env if not exists
# 4. Run setup wizard (python3 setup_wizard.py) — prompts for:
#    - Gemini API key (with link to get one free)
#    - Telegram bot token + chat ID (with step-by-step instructions)
#    - Gmail credentials (opens browser automatically)
#    - Outlook client ID (optional, skip if not NUS)
#    - GCal (optional)
# 5. docker compose up -d (starts Postgres)
# 6. cd infra && python3 -m alembic upgrade head (runs migrations)
# 7. claw init (creates default user)
# 8. claw status (confirms everything green)
# 9. Print: "✓ All set. Run 'claw worker start' to begin."
```

**setup_wizard.py** — interactive prompts using `questionary` or `rich`:
```
Welcome to Clawdbot setup!

Step 1/5: LLM Provider
  → Get a free Gemini API key at: https://aistudio.google.com/apikey
  Paste your Gemini API key: ___

Step 2/5: Telegram (receives your digests + reminders)
  → Create a bot: message @BotFather on Telegram → /newbot
  Bot token: ___
  → Start a chat with your bot, then visit:
    https://api.telegram.org/bot<TOKEN>/getUpdates
  Your chat ID: ___

Step 3/5: Gmail
  → Opening browser for Gmail authorization...

Step 4/5: Outlook / NUS Exchange (optional — press Enter to skip)
  ...

Step 5/5: Google Calendar (optional — press Enter to skip)
  ...

✓ Setup complete! Written to .env
```

---

## Task 2: Docker Compose Full Stack

**Goal:** `docker compose up -d` starts everything — DB, worker, API. No manual steps.

**Files:**
- Update: `docker-compose.yml` (add worker + API services)
- Create: `apps/worker/Dockerfile`
- Create: `apps/api/Dockerfile`

**docker-compose.yml:**
```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: clawdbot
      POSTGRES_PASSWORD: clawdbot
      POSTGRES_DB: clawdbot
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "clawdbot"]
      interval: 5s

  migrate:
    build: .
    command: sh -c "cd infra && python3 -m alembic upgrade head"
    depends_on:
      db:
        condition: service_healthy
    env_file: .env

  worker:
    build: apps/worker/
    command: python3 -c "from worker.main import start; start()"
    depends_on:
      migrate:
        condition: service_completed_successfully
    env_file: .env
    restart: unless-stopped
    volumes:
      - ~/.config/clawdbot:/root/.config/clawdbot  # Gmail token

  api:
    build: apps/api/
    ports:
      - "8000:8000"
    depends_on:
      migrate:
        condition: service_completed_successfully
    env_file: .env
    restart: unless-stopped

volumes:
  pgdata:
```

**Result:** After setup, just run `docker compose up -d` and walk away. The worker polls forever, restarts on crash.

---

## Task 3: Telegram Interactive Bot

**Goal:** When Clawdbot extracts a task, it sends a Telegram message with buttons: **Accept** / **Dismiss** / **Snooze 2h**. You tap one button and it's done — no terminal.

**New file:** `packages/core/src/core/telegram_bot.py`

**Library:** `python-telegram-bot` (already in deps as `python-telegram-bot`) or switch to `aiogram` for async.

**Flows:**

### Task approval (sent after extraction):
```
📋 New task from Google Security Alert:
"Check account activity for unauthorized access"
Priority: 85  |  No due date

[✓ Accept]  [✗ Dismiss]  [⏰ Snooze 2h]
```
→ User taps → bot sends confirmation → DB updated

### Morning briefing (7am, replaces plain text):
```
☀️ Good morning, Aryan — Mon 3 Mar

📌 DUE TODAY
  Nothing due

📅 UPCOMING
  • CS3230 Problem Set 4 — due Fri

📬 INBOX (8 new)
  3 actionable  |  5 filtered

PVI: 50 (normal) ████░░░░░░

[View tasks]  [View inbox]  [Snooze all]
```

### Commands the bot understands:
```
/tasks     — show open tasks with Accept/Dismiss buttons
/inbox     — show last 5 emails with summaries
/digest    — trigger manual digest
/pvi       — show today's PVI
/focus 30m — start focus mode for 30 min
/status    — system health
```

**Implementation:**
- Add a new job `job_run_telegram_bot()` to the worker that runs the bot in polling mode
- Bot uses webhook or long-polling
- Callback handlers update the DB directly

---

## Task 4: Telegram Email Reply Workflow

**Goal:** For emails that need replies, Clawdbot sends the full thread + your intent → LLM drafts → you approve in Telegram → it sends.

**Flow:**
```
[New email detected that likely needs reply]
         ↓
Telegram message:
  📨 Reply needed — from alice@nus.edu.sg
  Subject: "Group project meeting time"

  Thread summary:
  Alice asked about meeting time for CS3230 project.

  [Draft reply]  [Skip]

User taps "Draft reply" →

  Bot: "What do you want to say? (just the gist)"
  User: "Saturday 3pm works for me, share zoom link"

  Bot calls LLM with full thread + gist →

  ✉️ Draft reply:
  "Hi Alice, Saturday at 3pm works well for me!
   Could you share the Zoom link when you have it?
   Looking forward to the meeting. Best, Aryan"

  [✓ Send]  [✏️ Edit]  [✗ Cancel]

User taps Send → Gmail API sends it → "✓ Sent"
```

**New files:**
- `packages/core/src/core/llm/reply_crafter.py` — takes thread + gist → drafts reply
- Update `telegram_bot.py` — add conversation handler for reply flow

---

## Task 5: Canvas / NUS Notifications Push

**Goal:** When a Canvas assignment is detected, immediately push to Telegram with the deadline. No waiting for the daily digest.

**Flow:**
```
Canvas email detected during sync
         ↓
Telegram push (immediate, not waiting for digest):

  📚 New Canvas assignment — CS3230
  "Problem Set 4"
  Due: Friday, 7 Mar at 11:59pm

  [Add to tasks]  [View on Canvas]
```

**Implementation:**
- In `normalizer.py`, after Canvas detection, call `send_message()` directly
- Add Canvas-specific Telegram template

---

## Task 6: System Health Alerts

**Goal:** When something breaks or needs attention, Clawdbot tells you what to fix — never silently fails.

**Alerts to implement:**

| Trigger | Telegram message |
|---------|-----------------|
| LLM extraction fails 3x in a row | "⚠️ LLM extraction failing. Check your Gemini API key / credits." |
| Gmail token expired | "⚠️ Gmail auth expired. Run: claw connect gmail" |
| Outlook token expired | "⚠️ Outlook auth expired. Run: claw connect outlook" |
| DB connection fails | "🔴 Database unreachable. Check Postgres is running." |
| GCal 403 (API disabled) | "⚠️ Google Calendar API disabled. Enable it at: [link]" |
| No sync in >30 min | "⚠️ No emails synced in 30 minutes — worker may have crashed." |
| LLM triage rate >90% | "ℹ️ 90%+ emails being filtered. Your label filter may be too broad." |

**New file:** `packages/core/src/core/health.py`

```python
def alert(message: str, level: str = "warning") -> None:
    """Send a system health alert to Telegram. Never raises."""
    emoji = {"warning": "⚠️", "error": "🔴", "info": "ℹ️"}.get(level, "⚠️")
    try:
        send_message(f"{emoji} *Clawdbot Alert*\n{message}")
    except Exception:
        pass  # health alerts must never crash the caller
```

**Usage in jobs.py:**
```python
except Exception as exc:
    alert(f"Gmail poll failed: {exc}", level="error")
    log.error("job_poll_gmail_failed", error=str(exc))
    # continue — don't crash the scheduler
```

---

## Task 7: Error Resilience

**Goal:** No single failure kills the worker. Every job catches its own exceptions and reports via health alerts.

**Pattern for all jobs:**
```python
def job_poll_and_normalize():
    try:
        _do_poll()
    except GmailAuthError:
        alert("Gmail auth expired. Run: claw connect gmail")
    except Exception as exc:
        alert(f"Gmail poll failed: {exc}", level="error")
        log.error("job_poll_failed", error=str(exc))
```

**Specific resilience to add:**
- Circuit breaker for LLM calls (after 5 consecutive failures, pause extraction for 10 min)
- Gmail history cursor recovery (if historyId expires, fall back to full poll — already partially done)
- Retry with exponential backoff for transient API errors (429, 503)
- Worker restart detection (if worker hasn't polled in 30min, alert)

**New file:** `packages/core/src/core/circuit_breaker.py`

---

## Task 8: Multi-User Support

**Goal:** Friends can clone the repo and each get their own isolated environment. Each user has their own Gmail, Telegram chat, credentials.

**Changes needed:**
- `setup.sh` creates a user-specific `.env` (or `.env.username`)
- `claw init` prompts for name + creates a user row
- `default_user_id` becomes per-user (stored in `.env`)
- Telegram `chat_id` is per-user
- Credentials stored under user-specific keyring service names

**For easy friend setup:**
- `README.md` with step-by-step setup (5 steps, screenshots)
- `setup.sh` handles all dependencies automatically
- Works on Mac, Linux (WSL on Windows)

---

## Task 9: Web Dashboard

**Goal:** A simple, clean web UI for people who prefer browser over terminal/Telegram.

**Stack:** FastAPI (already exists) + HTMX (no React complexity) or minimal React.

**Pages:**
- `/` — dashboard (PVI, tasks due today, recent emails)
- `/inbox` — email list with summaries, Canvas flagged
- `/tasks` — task list with Accept/Done/Dismiss buttons
- `/digest` — today's digest + weekly review
- `/reply/<id>` — view + approve draft reply
- `/settings` — connect Gmail/Outlook/GCal, configure Telegram

**Auth:** Single-user, simple API key in `.env` (no OAuth needed for personal use).

---

## Task 10: Deployment

**Goal:** Run on a cheap VPS (DigitalOcean $4/mo, Railway, Fly.io) with zero downtime.

**Options (in order of ease):**

### Option A: Railway (easiest, ~$5/mo)
```bash
railway login
railway init
railway add --database postgresql
railway up
```
Railway auto-deploys on git push, provides Postgres, runs Docker Compose.

### Option B: Fly.io (~$3/mo)
```bash
fly launch
fly postgres create
fly deploy
```

### Option C: Self-hosted VPS (most control)
```bash
# On VPS:
git clone <repo>
./setup.sh
docker compose up -d
# Done — runs forever, restarts on reboot via restart: unless-stopped
```

**What runs where:**
- Postgres: managed DB (Railway/Fly) or Docker on VPS
- Worker: Docker container, `restart: unless-stopped`
- API/Web: Docker container, behind nginx
- Gmail credentials: mounted volume (not committed to git)

**Domain:** Optional Cloudflare tunnel for web dashboard access (free, no port forwarding).

---

## Suggested Build Order (Updated)

```
✅ Week 1: Resilience (DONE)
  Task 6 (health alerts)  ✅
  Task 7 (resilience)     ✅

Week 2: Deployment + Telegram Power (NEXT)
  Task 2 (Docker stack)      — enables persistent deployment
  Task 3 (interactive bot)   — biggest daily UX win
  Task 4 (reply workflow)    — flagship feature
  Task 5 (Canvas push)       — immediate NUS value

Week 3: Polish + Scale
  Task 1 (setup.sh)     — unblocks friends from using it
  Task 2 (Docker stack) — enables persistent deployment
  Task 7 (resilience)   — makes it safe to run 24/7

Week 2: Telegram Power
  Task 3 (interactive bot)   — biggest daily UX win
  Task 4 (reply workflow)    — flagship feature
  Task 5 (Canvas push)       — immediate NUS value
  Task 6 (health alerts)     — never dark silently

Week 3: Polish + Scale
  Task 8 (multi-user)   — share with friends
  Task 9 (web dashboard)
  Task 10 (deployment)
```

---

## Quick Wins (can do in 1 session each)

1. **Canvas push** — 50 lines in normalizer.py + telegram_client.py
2. **Health alerts** — health.py + wrap all jobs in try/except with alert()
3. **`.env.example`** — document every variable with comments
4. **`README.md`** — proper setup guide with screenshots
5. **`setup.sh`** — basic version (install deps, copy .env.example, run migrations)
