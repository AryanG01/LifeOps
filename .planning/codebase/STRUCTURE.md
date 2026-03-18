# Codebase Structure

**Analysis Date:** 2026-03-19

## Directory Layout

```
/Users/aryanganju/Desktop/Code/LifeOps/
├── packages/              # Shared libraries (published as installable packages)
│   ├── core/             # Core domain logic (DB, models, pipelines, LLM, policies)
│   ├── connectors/       # Email/calendar ingestion (Gmail, Outlook, GCal, Canvas)
│   └── cli/              # Command-line interface (Typer app + command modules)
├── apps/                 # Runnable applications (API, worker, bot, web)
│   ├── api/              # FastAPI web dashboard + REST endpoints
│   ├── worker/           # APScheduler background job orchestrator
│   ├── bot/              # Telegram interactive bot (python-telegram-bot v20)
│   └── web/              # (Placeholder for future Next.js/React frontend)
├── infra/                # Database & deployment infrastructure
│   ├── alembic/          # Database migrations (SQLAlchemy DDL)
│   ├── docker-compose.yml # 5-service stack (db, api, worker, bot, web)
│   └── scripts/          # Setup/utility scripts
├── docs/                 # Documentation (deployment guide, plans)
├── tests/                # Pytest test suite (unit + integration)
├── credentials/          # Local service account files (git-ignored)
├── .env.example          # Template for environment configuration
└── CLAUDE.md             # Claude code rules (context, patterns)
```

## Directory Purposes

**`packages/core/src/core/`:**
- Purpose: Domain logic, database layer, pipeline orchestration, LLM integration, policies
- Contains: Config, DB engine, ORM models, normalizer, LLM extractor, PVI engine, digest generator, reminders, notifications, circuit breaker, health alerts
- Key files:
  - `config.py` — Settings singleton (reads from .env)
  - `db/engine.py` — `get_db()` context manager (auto-commit, rollback)
  - `db/models.py` — 16 ORM models (User, Source, Message, ActionItem, Reminder, Policy, PVIDailyFeature, etc.)
  - `pipeline/normalizer.py` — Raw event → Message (deduplication)
  - `llm/extractor.py` — LLM extraction driver (dual-model: Gemini + Anthropic)
  - `pvi/engine.py` — Workload scoring and policy computation
  - `digest/generator.py` — Daily digest markdown generation
  - `pipeline/reminders.py` — Reminder scheduling and dispatch
  - `telegram_notify.py`, `telegram_client.py` — Telegram message pushing
  - `circuit_breaker.py` — LLM failure resilience
  - `health.py` — Rate-limited alerting

**`packages/connectors/src/connectors/`:**
- Purpose: Email and calendar synchronization connectors
- Contains: Pollers for Gmail, Outlook, Google Calendar; Canvas email parser; OAuth handlers
- Key files:
  - `gmail/poller.py` — History API delta polling (incremental sync with historyId)
  - `gmail/auth.py` — OAuth2 credentials management
  - `outlook/poller.py` — Microsoft Graph delta token sync
  - `outlook/auth.py` — MSAL device code flow (AADSTS50059 fix: tenant="organizations")
  - `gcal/poller.py` — Google Calendar 14-day event window
  - `canvas/parser.py` — Canvas LMS email body extraction

**`packages/cli/src/cli/`:**
- Purpose: User-facing command-line interface
- Contains: Typer CLI app, command modules
- Key files:
  - `main.py` — Root CLI app, command registry (connect, sync, tasks, inbox, digest, pvi, bot, worker, reply, focus, etc.)
  - `commands/init.py` — Email-based user creation, writes DEFAULT_USER_ID to .env
  - `commands/sync.py` — Manual sync trigger
  - `commands/digest.py`, `commands/pvi.py` — View digest/PVI for specific date
  - `commands/tasks.py`, `commands/inbox.py` — Query and manage tasks/messages
  - `commands/reply.py` — View and send email replies (LLM-drafted)
  - `commands/focus.py` — Enter/exit focus mode (silence Telegram reminders)
  - `commands/bot.py` — Launch Telegram bot (`claw bot start`)
  - `commands/worker.py` — Launch background job scheduler (`claw worker start`)
  - `commands/status.py` — Show user, sources, heartbeat status

**`apps/api/src/api/`:**
- Purpose: Web dashboard + REST API for task/message/PVI queries
- Contains: FastAPI app, routes, Jinja2 templates, auth
- Key files:
  - `main.py` — FastAPI app, Jinja2 template routes (`/`, `/tasks`, `/inbox`), route includes (sync, inbox, tasks, digest, pvi, replay, dashboard_api)
  - `routes/dashboard_api.py` — `/api/tasks`, `/api/messages`, `/api/pvi/today`, accept/dismiss mutations
  - `routes/digest.py` — GET/POST digest endpoints
  - `routes/pvi.py` — GET pvi by date
  - `routes/sync.py` — POST to trigger sync manually
  - `routes/replay.py` — Replay extraction/normalization for debugging
  - `auth.py` — APIKeyHeader validation (gated by `dashboard_api_key` setting)
  - `templates/base.html` — Base layout with CSS/HTMX scripts
  - `templates/dashboard.html` — Main dashboard view
  - `templates/tasks.html` — Task list with HTMX interactions
  - `templates/inbox.html` — Message list with summaries

**`apps/worker/src/worker/`:**
- Purpose: Background job orchestration via APScheduler
- Contains: Job definitions, APScheduler configuration
- Key files:
  - `jobs.py` — 8 job functions:
    - `job_poll_and_normalize()` — every 15 min
    - `job_extract_pending()` — every 5 min (circuit breaker protected)
    - `job_schedule_reminders()` — every 10 min
    - `job_poll_outlook()` — every 15 min
    - `job_poll_gcal()` — every 60 min
    - `job_meeting_prep()` — every 30 min
    - `job_daily_pvi_and_digest()` — 7am daily (cron)
    - `job_heartbeat()` — every 5 min (stale poll detection)
  - `main.py` — APScheduler app setup, job registration, run()

**`apps/bot/src/bot/`:**
- Purpose: Telegram interactive bot interface
- Contains: Bot handlers, command processors, inline keyboards
- Key files:
  - `main.py` — Build and run Telegram bot (python-telegram-bot v20, Application + handlers)
  - `handlers/commands.py` — Command handlers (`/tasks`, `/inbox`, `/digest`, `/pvi`, `/newtask`, `/status`, `/focus`, `/reply`)
  - `handlers/callbacks.py` — Inline button callback handlers (task approve/dismiss, reply send)
  - `keyboards.py` — Keyboard builders (inline buttons for task actions, reply options)

**`infra/`:**
- Purpose: Database, migrations, infrastructure-as-code
- Contains: Alembic migrations, Docker Compose, deployment configs
- Key files:
  - `alembic/env.py` — Migration runner (configures SQLAlchemy URL from settings)
  - `alembic/versions/0001_initial_schema.py` — Initial schema (users, sources, raw_events, messages, etc.)
  - `alembic/versions/0002_phase2_tables.py` — Extended schema (action_items, reminders, policies, etc.)
  - `docker-compose.yml` — 5-service stack (postgres:17, api:8000, worker, bot, web)
  - `scripts/` — Setup helper scripts

**`docs/`:**
- Purpose: User and developer documentation
- Contains: Deployment guide, planning docs, phase notes
- Key files:
  - `deployment.md` — Railway/Fly.io/VPS/Oracle Cloud deployment guide
  - `plans/` — Phase planning and progress tracking

**`tests/`:**
- Purpose: Automated testing (135/135 unit tests passing)
- Contains: Unit and integration tests
- Key files:
  - `unit/` — Tests for individual modules (normalizer, LLM, PVI, reminders, pollers, etc.)
  - `integration/` — End-to-end pipeline tests
  - `conftest.py` — Pytest fixtures and config

## Key File Locations

**Entry Points:**
- CLI: `packages/cli/src/cli/main.py` — Typer root app
- API: `apps/api/src/api/main.py` — FastAPI app (listen on api_host:api_port)
- Worker: `apps/worker/src/worker/main.py` — APScheduler job runner
- Bot: `apps/bot/src/bot/main.py` — Telegram bot (long-polling)

**Configuration:**
- `.env` — Runtime secrets (LLM keys, DB URL, Telegram token, OAuth credentials)
- `.env.example` — Template with all required fields
- `packages/core/src/core/config.py` — Settings singleton (Pydantic BaseSettings)

**Core Logic:**
- Data models: `packages/core/src/core/db/models.py` (16 ORM classes)
- DB context: `packages/core/src/core/db/engine.py` (get_db() context manager)
- Event normalization: `packages/core/src/core/pipeline/normalizer.py`
- LLM extraction: `packages/core/src/core/llm/extractor.py`
- Reminder scheduling: `packages/core/src/core/pipeline/reminders.py`
- PVI/policy computation: `packages/core/src/core/pvi/engine.py`
- Digest generation: `packages/core/src/core/digest/generator.py`

**Testing:**
- Pytest fixtures: `tests/conftest.py`
- DB connection for tests: Uses `conftest.py` to set PYTHONPATH, mocks with SQLAlchemy session
- Test databases: Separate test DB per test (in-process SQLite or Postgres)

## Naming Conventions

**Files:**
- Snake_case for all Python files: `gmail_poller.py`, `extract_all_pending.py`
- Modules correspond to functions: `reminders.py` contains reminder logic
- Directories are plural (collectors) or plural nouns (connectors, handlers): `packages/connectors/`, `apps/bot/handlers/`

**Directories:**
- `packages/` — Reusable libraries (core, connectors, cli)
- `apps/` — Runnable applications (api, worker, bot, web)
- `src/<package_name>/` — Source layout for PEP 517 editable installs
- `commands/` — CLI command modules
- `handlers/` — Telegram bot event handlers
- `routes/` — FastAPI route modules
- `templates/` — Jinja2 HTML templates
- `alembic/versions/` — Migration files

**Functions & Classes:**
- Classes: `PascalCase` (User, Message, ActionItem, ExtractionResult)
- Functions: `snake_case` (poll_gmail, normalize_all_pending, dispatch_due_reminders)
- Private functions: Leading underscore (_extract_fields_from_payload, _call_llm)
- Job functions: `job_*` (job_poll_and_normalize, job_extract_pending)

**Database:**
- Table names: `snake_case` plural (users, messages, action_items, reminders)
- Column names: `snake_case` (user_id, created_at, is_active)
- Foreign keys: Suffix `_id` (user_id, message_id, action_item_id)
- Status/type enums: `snake_case` lowercase ("pending", "active", "done", "dismissed")

**Environment Variables:**
- All caps with underscores: `GEMINI_API_KEY`, `DATABASE_URL`, `TELEGRAM_BOT_TOKEN`
- Config keys: Python snake_case (parsed by Pydantic from env)

## Where to Add New Code

**New Feature (Task Management, Reminders, etc.):**
- Core logic: `packages/core/src/core/pipeline/` or `packages/core/src/core/<domain>/`
- ORM model: Add class to `packages/core/src/core/db/models.py`
- Migration: Create new `infra/alembic/versions/NNNN_*.py`
- Tests: `tests/unit/test_<feature>.py` or `tests/integration/test_<feature>.py`
- CLI command: `packages/cli/src/cli/commands/<feature>.py` + register in `main.py`
- Background job: Add function to `apps/worker/src/worker/jobs.py` + register in `main.py`

**New Connector (Email/Calendar Source):**
- Poller: `packages/connectors/src/connectors/<source>/poller.py`
- Auth: `packages/connectors/src/connectors/<source>/auth.py` (if needed)
- Pattern:
  - Implement `poll_<source>(user_id, source_id)` function
  - Create RawEvent rows for new messages/events
  - Update Source.sync_cursor with pagination token
  - Raise RuntimeError("not connected") if auth fails
  - Call from `apps/worker/src/worker/jobs.py` job function

**New API Endpoint:**
- FastAPI route: Create `apps/api/src/api/routes/<resource>.py`
- Include in `apps/api/src/api/main.py` with `app.include_router()`
- Pattern:
  - Use `@router.get()` or `@router.post()` decorator
  - Lazy import `get_db()` inside function
  - Query with `with get_db() as db: db.query(...)`
  - Return dict/list of dicts (JSON serializable)

**New Telegram Bot Command:**
- Handler: `apps/bot/src/bot/handlers/commands.py` or new `handlers/<feature>.py`
- Register in `apps/bot/src/bot/main.py` with `app.add_handler(CommandHandler(...))`
- Callback (inline buttons): `apps/bot/src/bot/handlers/callbacks.py`
- Keyboard builder: Add to `apps/bot/src/bot/keyboards.py`
- Pattern:
  - `async def handle_<command>(update, context)` for command handler
  - Send to Telegram via `await update.message.reply_text()` or `send_task_notification()`

**Utilities/Helpers:**
- Shared helpers: `packages/core/src/core/<domain>/` (e.g., `packages/core/src/core/calendar/prep.py`)
- Database-agnostic utilities: `packages/core/src/core/` root level
- Connector-specific utilities: `packages/connectors/src/connectors/<source>/`

## Special Directories

**`credentials/`:**
- Purpose: Store local OAuth credentials and service account files
- Generated: Yes (created by `claw connect gmail` / `claw connect outlook`)
- Committed: No (in .gitignore)
- Contents:
  - `gmail_credentials.json` — OAuth2 refresh token for Gmail
  - `.msal_cache` — Outlook token cache

**`.env`:**
- Purpose: Runtime configuration and secrets
- Generated: Yes (created by `setup.sh` or `setup_wizard.py`)
- Committed: No (in .gitignore; .env.example is committed)
- Contents: LLM keys, database URL, Telegram token, OAuth client IDs, user settings

**`infra/alembic/versions/`:**
- Purpose: Versioned database schema migrations
- Generated: Yes (hand-written migrations via `python3 -m alembic revision`)
- Committed: Yes (part of source control)
- Pattern: One file per migration, numbered (0001, 0002, etc.)

**`.pytest_cache/`:**
- Purpose: Pytest internal cache
- Generated: Yes (auto-created by pytest)
- Committed: No (in .gitignore)

**`.planning/codebase/`:**
- Purpose: GSD codebase analysis documents (this file and others)
- Generated: Yes (created by gsd-codebase-mapper agent)
- Committed: Yes (useful for future phases)

---

*Structure analysis: 2026-03-19*
