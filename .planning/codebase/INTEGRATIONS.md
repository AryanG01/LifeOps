# External Integrations

**Analysis Date:** 2026-03-19

## APIs & External Services

**Email & Calendar:**
- **Gmail** - Email ingestion and send
  - SDK/Client: google-api-python-client
  - Auth: OAuth 2.0 (installed app flow, PKCE)
  - Implementation: `packages/connectors/src/connectors/gmail/`
  - Scopes: gmail.readonly, gmail.labels, gmail.send, calendar.readonly
  - Polling: History API delta sync (every 15 minutes, configurable)
  - Credentials file: `~/.config/clawdbot/gmail_credentials.json`

- **Google Calendar** - Calendar event ingestion (14-day rolling window)
  - SDK/Client: google-api-python-client
  - Auth: OAuth 2.0 (same credentials as Gmail)
  - Implementation: `packages/connectors/src/connectors/gcal/poller.py`
  - Polling: Every 15 minutes

- **Outlook/Microsoft Graph** - Alternative email source for Microsoft 365 tenants
  - SDK/Client: msal (Microsoft Authentication Library)
  - Auth: Device code flow (user visits https://microsoft.com/devicelogin and enters code)
  - Scopes: Mail.Read, Calendars.Read, User.Read
  - Tenant: Configurable (default "common", override to "organizations" or specific domain like "nus.edu.sg")
  - Implementation: `packages/connectors/src/connectors/outlook/`
  - Secure token storage via keyring

**LLM Services:**
- **Google Gemini** (default, free tier)
  - SDK/Client: openai (OpenAI-compatible endpoint)
  - API Key env var: `GEMINI_API_KEY`
  - Model: gemini-2.5-flash (default), gemini-2.5-flash-lite (triage)
  - Endpoint: https://generativelanguage.googleapis.com/v1beta/openai/
  - Rate limit: 250 req/day, 10 RPM for free tier
  - JSON mode: Enabled (response_format={"type": "json_object"})
  - Implementation: `packages/core/src/core/llm/extractor.py` (_call_gemini)

- **Anthropic Claude** (alternative)
  - SDK/Client: anthropic
  - API Key env var: `ANTHROPIC_API_KEY`
  - Model: claude-sonnet-4-6 (configurable)
  - Implementation: `packages/core/src/core/llm/extractor.py` (_call_anthropic)
  - Provider selection: `llm_provider` setting ("gemini" or "anthropic")

**Canvas LMS:**
- Parsed via email detection patterns (NUS-specific: canvas.nus.edu.sg, course code format)
- No direct API integration — Canvas notifications arrive via Gmail as emails
- Parser: `packages/connectors/src/connectors/canvas/parser.py`
- Patterns: Detects sender (instructure.com, nus.edu.sg), subjects (assignment, announcement, due, etc.)
- Extraction: Course codes (CS3230, MA1101R, etc.), due dates, Canvas URLs

## Data Storage

**Database:**
- **PostgreSQL 16+**
  - Connection: `DATABASE_URL` env var (default: postgresql://clawdbot:clawdbot@localhost:5432/clawdbot)
  - Client: SQLAlchemy 2.0+ ORM
  - Migrations: Alembic (managed via `infra/alembic/`, run with `cd infra && python3 -m alembic upgrade head`)
  - 16 ORM models: User, Source, RawEvent, Message, MessageSummary, MessageLabel, ReplyDraft, LLMRun, ActionItem, Reminder, PVIDailyFeature, PVIDailyScore, Policy, Digest, CalendarEvent, FocusSession
  - All models use UUID primary keys (PostgreSQL native UUID type)
  - Models defined: `packages/core/src/core/db/models.py`
  - Engine/session: `packages/core/src/core/db/engine.py` (get_db() context manager with auto-commit)

**File Storage:**
- Local filesystem only (no cloud storage integration)
- OAuth credentials: System keyring via `core.tokens.store_token()/get_token()`
- Gmail credentials file: `~/.config/clawdbot/gmail_credentials.json` (OAuth installed-app credentials)

**Caching:**
- None (direct database queries, no Redis or memcache)
- Oauth tokens cached in system keyring

## Authentication & Identity

**Auth Providers:**
- **Gmail OAuth 2.0** - Installed application flow with PKCE
  - Token storage: System keyring (via keyring package)
  - Service name: "clawdbot-gmail"
  - Refresh flow: Automatic (google-auth refreshes expired tokens)

- **Outlook/Microsoft Graph MSAL** - Device code flow
  - Token storage: System keyring
  - Service name: Configurable (default "clawdbot-outlook")
  - Authority: https://login.microsoftonline.com/{OUTLOOK_TENANT}
  - Tenant resolution: From config.outlook_tenant setting (default "common", override to "organizations" for Azure apps)

- **Telegram Bot API** - Token-based
  - Token: `TELEGRAM_BOT_TOKEN` env var
  - Chat ID: `TELEGRAM_CHAT_ID` env var (destination for notifications)
  - No user auth — bot sends unilateral messages to configured chat

- **Web Dashboard API Key** - Simple header/query auth (optional)
  - Key: `DASHBOARD_API_KEY` env var (empty string disables auth)
  - Implementation: `apps/api/src/api/auth.py` (APIKeyHeader/Query validators)

**User Management:**
- Email-based user creation (idempotent via `claw init` command)
- Multi-user support: Each user has UUID, email, timezone, display_name
- Default user: Singleton UUID (00000000-0000-0000-0000-000000000001) for single-user deployments
- User ID written to `.env` as `DEFAULT_USER_ID` by setup_wizard.py

## Monitoring & Observability

**Error Tracking:**
- None detected (no Sentry, DataDog, etc.)
- Alerts via system health module: `core.health.alert(key, message, level, cooldown_minutes)`
- Rate-limited alerts prevent notification spam (default: cooldown_minutes configurable)

**Logs:**
- Structured logging via structlog 24.0+
- Format: JSON-compatible by default
- Implementation: All modules use `log = structlog.get_logger()`
- No log aggregation service detected (local only)

**Circuit Breaker:**
- LLM circuit breaker: `core.circuit_breaker.llm_breaker`
- Opens after 5 consecutive LLM failures, pauses extraction for 10 minutes
- Prevents cascade failures when LLM service is unavailable
- Implementation: `packages/core/src/core/circuit_breaker.py`

**Health Checks:**
- Docker Compose health check: PostgreSQL readiness (pg_isready)
- System health job: `job_heartbeat()` in worker, checks poll freshness
- Stale poll detection: Alerts if no data ingested for 30+ minutes

## CI/CD & Deployment

**Hosting:**
- Railway (platform.railway.app)
- Fly.io (fly.io)
- VPS (DigitalOcean, Linode, custom)
- Oracle Cloud Free Tier
- Docker Compose local development

**CI Pipeline:**
- GitHub Actions (none detected in codebase, assumed from GitHub repo)
- Local testing via pytest (`python3 -m pytest tests/unit/ -v`)

**Deployment Configs:**
- `fly.toml` - Fly.io configuration
- `railway.toml` - Railway configuration
- `.railway.json` - Railway alternate config
- `infra/docker-compose.yml` - Local/self-hosted containerized stack
- `infra/Dockerfile.migrate` - Alembic migration container
- `apps/{api,worker,bot}/Dockerfile` - Individual service containers

**Database Migrations:**
- Alembic (SQLAlchemy migration tool)
- Configuration: `infra/alembic.ini`
- Migrations run as container service before api/worker/bot start
- Migration container: `infra/Dockerfile.migrate`

## Environment Configuration

**Required env vars:**
- `DATABASE_URL` - PostgreSQL connection (default provided)
- `GEMINI_API_KEY` or `ANTHROPIC_API_KEY` - LLM provider credentials
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` - Telegram push notifications
- `OUTLOOK_CLIENT_ID` - Azure app registration (if using Outlook)
- `OUTLOOK_TENANT` - Azure tenant ID or "organizations" (default "common")
- `USER_EMAIL` - Primary user email (for multi-user context)

**Optional:**
- `GMAIL_CREDENTIALS_PATH` - Path to Gmail OAuth credentials file (default: ~/.config/clawdbot/gmail_credentials.json)
- `LLM_PROVIDER` - "gemini" (default) or "anthropic"
- `LLM_TRIAGE_ENABLED` - Enable lightweight LLM filtering (default: True)
- `LLM_TRIAGE_MODEL` - Lightweight model (default: gemini-2.5-flash-lite)
- `TELEGRAM_ENABLED` - Boolean flag (default: False)
- `BOT_NOTIFY_MIN_PRIORITY` - Minimum priority for Telegram push (0-100, default: 60)
- `PRIVACY_STORE_FULL_BODIES` - Store full email bodies or preview only (default: True)
- `PRIVACY_REDACT_EMAILS` - Redact sender emails in logs (default: False)
- `USER_TIMEZONE` - Timezone for user (default: Asia/Singapore)
- `API_HOST`, `API_PORT` - FastAPI binding (default: 127.0.0.1:8000)
- `DASHBOARD_API_KEY` - Optional API key for web dashboard (empty = no auth)

**Secrets location:**
- `.env` file at project root (git-ignored)
- `.env.example` provided as template
- System keyring for OAuth tokens (via keyring package)

## Webhooks & Callbacks

**Incoming:**
- Telegram callback queries (inline button actions: accept, dismiss, snooze)
- Endpoints: `apps/bot/src/bot/handlers/callbacks.py`
- No HTTP webhooks from external services detected

**Outgoing:**
- Telegram message send: https://api.telegram.org/bot{token}/sendMessage (httpx POST)
- Gmail send: google-api-python-client (Gmail API)
- No outbound webhooks to external services detected

**Message Flow:**
1. Gmail/Outlook → Raw events in DB (via polling)
2. Raw events → Normalized messages (via job_poll_and_normalize)
3. Messages → LLM extraction (via job_extract_pending)
4. Extraction → Action items, reminders (with Telegram push if priority >= threshold)
5. Telegram callback → Action item status update in DB
6. Reminders due → Dispatch to Telegram/CLI/email
7. Daily digest generation → Push to Telegram at 7am

---

*Integration audit: 2026-03-19*
