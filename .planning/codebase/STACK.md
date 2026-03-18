# Technology Stack

**Analysis Date:** 2026-03-19

## Languages

**Primary:**
- Python 3.11 - Core application logic, data processing, API backends

**Secondary:**
- Jinja2 - Web dashboard templates
- HTML/CSS - Dashboard UI

## Runtime

**Environment:**
- Python 3.11 (required >= 3.10 for most packages, >= 3.11 for main project)
- Docker containerized deployment (5 services: db, migrate, api, worker, bot)

**Package Manager:**
- UV (modern Python package manager, workspace-based)
- Lockfile: implicit (UV manages reproducibility)

## Frameworks & Core Libraries

**API & Web:**
- FastAPI 0.111+ - REST API server for dashboard and webhooks
- Uvicorn 0.29+ - ASGI server (uvicorn[standard])
- Jinja2 3.1+ - Template rendering for web dashboard
- python-multipart 0.0.9+ - Form data parsing

**CLI & TUI:**
- Typer 0.12+ - Command-line interface (claw command)
- Rich 13.0+ - Terminal formatting and progress indicators
- Textual 0.60+ - Terminal UI components

**Data & Database:**
- SQLAlchemy 2.0+ - ORM for PostgreSQL
- psycopg2-binary 2.9+ - PostgreSQL adapter
- Alembic 1.13+ - Database migrations (located at `infra/alembic`)
- Pydantic 2.0+ - Data validation
- pydantic-settings 2.0+ - Configuration management via environment

**Task Scheduling:**
- APScheduler 3.10+ - Job scheduling and background task execution
- Runs 8 recurring jobs: polling, extraction, reminders, digests, health checks

**LLM Integration:**
- openai 1.0+ - OpenAI-compatible client (Gemini API via OpenAI endpoint)
- anthropic 0.25+ - Anthropic Claude API (alternative provider)
- Both LLM providers supported via configurable `llm_provider` setting

**External APIs & Auth:**
- google-auth 2.29+ - Google OAuth 2.0 authentication
- google-auth-oauthlib 1.2+ - OAuth flow for installed applications
- google-api-python-client 2.125+ - Gmail API and Google Calendar API
- msal 1.28+ - Microsoft MSAL for Outlook/Microsoft Graph (device code flow)
- python-telegram-bot 20.0+ - Telegram Bot API wrapper
- python-dateutil 2.8+ - Date parsing and manipulation
- pytz 2024.1+ - Timezone handling

**Utility & Security:**
- keyring 24.0+ - Secure credential storage (system keyring via `core.tokens`)
- structlog 24.0+ - Structured logging (JSON-compatible)
- httpx 0.27+ - Async-capable HTTP client for Telegram and custom webhooks
- beautifulsoup4 4.12+ - HTML parsing (Canvas email extraction)
- lxml 5.0+ - XML/HTML parsing backend for BeautifulSoup

**Testing:**
- pytest - Test runner (configured in `pyproject.toml`)
- asyncio_mode: auto - For async test handling

## Package Structure

The project uses a monorepo workspace with 4 modular packages and 3 applications:

**Core Package** (`packages/core/`):
- Database models, ORM, migrations
- Configuration management
- LLM extraction pipeline
- Telegram notifications
- Health monitoring and circuit breaker
- PVI (Personal Vitality Index) computation
- Digest generation
- Token secure storage

**Connectors Package** (`packages/connectors/`):
- Gmail OAuth and polling (History API delta sync)
- Outlook/Microsoft Graph auth (device code flow) and polling
- Google Calendar polling
- Canvas email parser (NUS-specific detection)

**CLI Package** (`packages/cli/`):
- `claw` command entry point (`claw = "cli.main:app"`)
- Commands: connect, sync, today, focus, dash, digest, reply, bot, init, status

**API App** (`apps/api/`):
- FastAPI server (port 8000)
- Web dashboard (Jinja2 + HTMX)
- REST API: `/api/tasks`, `/api/messages`, `/api/pvi/today`
- API key authentication (optional, `dashboard_api_key` setting)

**Worker App** (`apps/worker/`):
- APScheduler background job runner
- 8 jobs: poll/normalize, extract, reminder dispatch, digest generation, etc.

**Bot App** (`apps/bot/`):
- Telegram bot handler
- Callback processors: accept/dismiss/snooze actions
- Message routing from Telegram to database

## Configuration

**Environment:**
- `.env` file (loads from project root via `Path(__file__).parent.parent.parent.parent.parent`)
- Pydantic BaseSettings with extra="ignore" (ignores unknown vars)
- `.env.example` provided as reference

**Key Settings:**
- `DATABASE_URL`: PostgreSQL connection string (default: localhost:5432/clawdbot)
- `LLM_PROVIDER`: "gemini" (default, free tier) or "anthropic"
- `GEMINI_API_KEY` / `ANTHROPIC_API_KEY`: LLM credentials
- `OUTLOOK_CLIENT_ID` / `OUTLOOK_TENANT`: Microsoft auth
- `GMAIL_CREDENTIALS_PATH`: OAuth credentials file location
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`: Telegram configuration
- `TELEGRAM_ENABLED`: Boolean flag for Telegram notifications
- `USER_TIMEZONE`: Default timezone (Asia/Singapore)
- `DEFAULT_USER_ID`: Single-user default UUID
- `API_HOST` / `API_PORT`: FastAPI server binding
- `DASHBOARD_API_KEY`: Optional API key for web dashboard access

**Build:**
- `pyproject.toml` at root and per-package
- `pytest.ini`: Test configuration (asyncio_mode=auto)
- `ruff` linting config: line-length=100

## Platform Requirements

**Development:**
- Python 3.11+ (interpreter)
- PostgreSQL 16 (database server)
- Docker & Docker Compose (for containerized dev/prod)
- UV package manager
- System keyring support (for token storage)

**Production:**
- PostgreSQL 16+ (database)
- Python runtime 3.11+
- Docker/Docker Compose OR direct installation + systemd
- Deployment targets: Railway, Fly.io, VPS, Oracle Cloud Free Tier (documented in `docs/deployment.md`)
- Fly.toml, railway.toml, .railway.json included for cloud deployments

**External Services:**
- Google Cloud (Gmail API, Google Calendar, Gemini API)
- Azure (Outlook/Microsoft Graph)
- Telegram Bot API (push notifications)
- Canvas LMS (NUS-specific, notification parsing)
- Anthropic Claude API (optional alternative to Gemini)

---

*Stack analysis: 2026-03-19*
