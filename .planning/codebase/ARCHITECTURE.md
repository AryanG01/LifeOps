# Architecture

**Analysis Date:** 2026-03-19

## Pattern Overview

**Overall:** Layered pipeline architecture with pluggable connectors, staged event processing, and policy-driven outputs.

**Key Characteristics:**
- Multi-stage event pipeline: poll → normalize → extract → schedule → dispatch
- Pluggable email/calendar source connectors (Gmail, Outlook, Google Calendar)
- LLM-powered message extraction with circuit breaker resilience
- Policy-driven digest generation and reminder cadences
- Multi-user support with message queuing and time-zone-aware scheduling
- Background job orchestration (APScheduler) + interactive bot (python-telegram-bot)

## Layers

**Connector Layer (Data Ingestion):**
- Purpose: Poll external email/calendar sources and ingest raw events
- Location: `packages/connectors/src/connectors/`
- Contains:
  - `gmail/poller.py` — History API delta polling (incremental sync)
  - `gmail/auth.py` — OAuth2 service account credentials
  - `outlook/poller.py` — Microsoft Graph delta token sync
  - `outlook/auth.py` — MSAL device code flow (multi-tenant NUS fix)
  - `gcal/poller.py` — Google Calendar 14-day event window
  - `canvas/parser.py` — Canvas LMS email parser
- Depends on: External APIs (Gmail, Graph, GCal), `core.db.engine` for persistence
- Used by: `worker/jobs.py` (poll_* jobs), CLI commands (`claw connect *`)

**Normalization Layer (Raw Event → Message):**
- Purpose: Transform raw payloads to canonical `Message` rows with deduplication
- Location: `packages/core/src/core/pipeline/normalizer.py`
- Contains:
  - `compute_dedup_hash()` — Stable SHA-256 hash from user_id, external_id, sender, subject
  - `_extract_fields_from_payload()` — Detect format (Gmail vs Outlook) and normalize
  - `normalize_all_pending()` — Idempotent batch processor (DB unique constraint enforced)
- Depends on: `core.db.models.RawEvent`, `core.db.models.Message`, connectors.canvas
- Used by: `job_poll_and_normalize()` in worker

**LLM Extraction Layer (Message → Task):**
- Purpose: Parse message content with LLM, generate task/summary/reply drafts
- Location: `packages/core/src/core/llm/`
- Contains:
  - `extractor.py` — Main extraction driver with dual-model support (Gemini + Anthropic)
  - `prompts/v1.py` — System + user prompts (JSON extraction with `extra=forbid`)
  - `schemas/llm.py` — Pydantic `ExtractionResult` model (strict validation)
- Depends on: `core.db.engine`, `core.circuit_breaker.llm_breaker`, external LLM APIs
- Used by: `job_extract_pending()` in worker, creates `ActionItem`, `MessageSummary`, `ReplyDraft` rows
- Resilience: Circuit breaker (5 consecutive failures → 10 min pause)

**Policy/PVI Layer (Situational Response):**
- Purpose: Compute daily workload index (PVI) and determine adaptive policies
- Location: `packages/core/src/core/pvi/engine.py`
- Contains:
  - `compute_features()` — Extract daily metrics (open tasks, overdue, inbox pressure, calendar load)
  - `score_from_features()` — Score 0-100 based on thresholds
  - `compute_pvi_daily()` — Store daily PVIDailyFeature + PVIDailyScore + Policy
- Depends on: `core.db.models.ActionItem`, `core.db.models.Message`, `core.db.models.Policy`
- Used by: `job_daily_pvi_and_digest()` at 7am, API `/pvi/today` endpoint
- Output: Regimes (overloaded/peak/normal/recovery) drive digest item limits, reminder cadences

**Reminder Pipeline (Task Scheduling):**
- Purpose: Create reminder rows at scheduled intervals; dispatch due reminders to channels
- Location: `packages/core/src/core/pipeline/reminders.py`
- Contains:
  - `CADENCES` map (gentle/standard/aggressive with hour-based offsets)
  - `schedule_reminders_for_task()` — Create Reminder rows with due_at = task.due_at - offset
  - `dispatch_due_reminders()` — Send pending reminders via Telegram or CLI
- Depends on: `core.db.models.Reminder`, `core.telegram_notify.send_task_notification()`
- Used by: `job_schedule_reminders()` in worker
- Respects: Focus sessions (`is_in_focus()`) to silence during DND periods

**Digest Generation Layer (Aggregation):**
- Purpose: Compile daily digest from tasks/messages/PVI; push to Telegram
- Location: `packages/core/src/core/digest/generator.py`
- Contains:
  - `generate_digest()` — Query tasks (due today/week), recent messages, format Markdown
  - Policy-driven item limits (PVI regime → max_digest_items)
  - Markdown formatting with priority icons (🔴/🟡/🟢)
- Depends on: `core.db.models.ActionItem`, `core.db.models.Message`, `core.db.models.Policy`
- Used by: `job_daily_pvi_and_digest()` at 7am
- Output: Pushed to Telegram via `send_digest()`

**API Layer (Web Dashboard + JSON):**
- Purpose: Serve web dashboard (Jinja2) + REST API for task/message/PVI queries
- Location: `apps/api/src/api/`
- Contains:
  - `main.py` — FastAPI app with Jinja2 template routes (`/`, `/tasks`, `/inbox`)
  - `routes/dashboard_api.py` — `/api/tasks`, `/api/messages`, `/api/pvi/today`, accept/dismiss endpoints
  - `auth.py` — APIKeyHeader validation (gated by `dashboard_api_key` setting)
  - `templates/` — base.html, dashboard.html, tasks.html, inbox.html (HTMX for interactivity)
- Depends on: `core.db.engine`, `core.config.get_settings()`
- Used by: Web browsers, HTMX frontend
- Port: Configurable (default 8000)

**Bot Layer (Telegram Interactive):**
- Purpose: Provide Telegram chat interface for viewing/creating tasks, digest, PVI, replies
- Location: `apps/bot/src/bot/`
- Contains:
  - `main.py` — Build Application (python-telegram-bot v20), register handlers, run long-polling
  - `handlers/commands.py` — `/tasks`, `/inbox`, `/digest`, `/pvi`, `/newtask`, `/status`, etc.
  - `handlers/callbacks.py` — Inline button taps (task approve/dismiss, reply send)
  - `keyboards.py` — Inline keyboard builders
- Depends on: `core.db.engine`, `core.telegram_notify.send_task_notification()`, `core.telegram_client`
- Used by: Telegram CLI (`claw bot start`) or direct invocation
- Interaction model: Long-polling with `drop_pending_updates=True`

**CLI Layer (User Commands):**
- Purpose: Command-line interface for setup, sync, viewing, and triggering jobs manually
- Location: `packages/cli/src/cli/`
- Contains:
  - `main.py` — Typer app entry point, command groups (connect, sync, tasks, inbox, digest, pvi, bot, worker)
  - `commands/` — Individual command modules (init, sync, digest, pvi, tasks, reply, focus, etc.)
  - Lazy imports inside command functions (avoid circular dependency on `core.config`)
- Depends on: All core modules, connectors
- Used by: Terminal, shell scripts, setup.sh

**Worker/Job Orchestration Layer:**
- Purpose: Schedule and execute background jobs on fixed intervals
- Location: `apps/worker/src/worker/`
- Contains:
  - `jobs.py` — 8 job functions (poll_gmail, poll_outlook, poll_gcal, extract, schedule_reminders, meeting_prep, daily_pvi_digest, heartbeat)
  - `main.py` — APScheduler setup: register jobs with cron/interval triggers
  - Circuit breaker integration for LLM extraction failures
  - Heartbeat monitoring for stale polls (>30 min → alert)
- Depends on: All pipeline modules, connectors
- Used by: Docker container (apps/worker) or `claw worker start`
- Timing:
  - `job_poll_and_normalize`: every 15 min
  - `job_extract_pending`: every 5 min (respects circuit breaker)
  - `job_schedule_reminders`: every 10 min
  - `job_poll_outlook`: every 15 min
  - `job_poll_gcal`: every 60 min
  - `job_meeting_prep`: every 30 min
  - `job_daily_pvi_and_digest`: 7am daily (cron)
  - `job_heartbeat`: every 5 min

## Data Flow

**Polling → Normalization → Extraction → Reminder → Dispatch:**

1. **Poll (every 15 min):**
   - `job_poll_and_normalize()` calls `poll_gmail(user_id, source_id)` for each Gmail source
   - Connector fetches new messages via History API, creates `RawEvent` rows
   - Normalizer idempotently converts to `Message` rows (unique on user_id, dedup_hash)

2. **Extract (every 5 min, circuit breaker protected):**
   - `job_extract_pending()` queries unprocessed `Message` rows (no `MessageSummary` yet)
   - For each message, calls configured LLM (Gemini or Anthropic)
   - Validates response with Pydantic `ExtractionResult` (extra=forbid), retries once on JSON error
   - Creates `ActionItem` (task), `MessageSummary` (urgency + summary), `ReplyDraft` (optional)
   - Records audit row in `LLMRun` (tokens, latency, validation status, attempt count)

3. **Schedule Reminders (every 10 min):**
   - `job_schedule_reminders()` queries active `ActionItem` rows with due_at set
   - For each task, calls `schedule_reminders_for_task(task_id, cadence)` where cadence from Policy
   - Creates `Reminder` rows at offsets (e.g., 72h, 48h, 24h, 8h, 4h before due)
   - Enforces unique constraint: (action_item_id, remind_at, channel) — idempotent

4. **Dispatch Reminders (every 10 min):**
   - `dispatch_due_reminders()` queries `Reminder` rows where remind_at <= now
   - Checks if user is in focus mode (`FocusSession.is_active` + not expired)
   - Sends to Telegram via `send_task_notification()` (inline keyboard with actions)
   - Updates reminder.status = "sent", reminder.sent_at = now

5. **Daily Digest & PVI (7am cron):**
   - `job_daily_pvi_and_digest()` runs for all users
   - Computes daily features (open tasks, overdue, incoming 24h, calendar minutes)
   - Scores features → determines regime (overloaded/peak/normal/recovery)
   - Writes `PVIDailyFeature`, `PVIDailyScore`, `Policy` rows
   - Calls `generate_digest()` — queries tasks due today/week, recent messages, formats Markdown
   - Sends to Telegram via `send_digest()`

**State Management:**

- **DB as source of truth:** All state persisted in PostgreSQL
  - `RawEvent` → incoming external data
  - `Message` → normalized, deduplicated
  - `MessageSummary` → LLM extraction output (urgency, summary, labels, replies)
  - `ActionItem` → tasks/todos extracted
  - `Reminder` → scheduled notifications
  - `PVIDailyFeature`/`PVIDailyScore`/`Policy` → adaptive policies
  - `FocusSession` → DND windows
- **Idempotent operations:** All background jobs safely rerunnable (unique constraints, status checks)
- **Transaction semantics:** `get_db()` context manager auto-commits on clean exit, rolls back on exception
- **No in-memory state:** Workers are stateless; all retry logic in DB

## Key Abstractions

**Source (Email/Calendar Connector):**
- Purpose: Abstract email account (Gmail/Outlook) or calendar (GCal)
- Examples: `packages/connectors/src/connectors/gmail/poller.py`, `packages/connectors/src/connectors/outlook/poller.py`
- Pattern:
  - Store `sync_cursor` (historyId or deltaToken) in `Source.sync_cursor`
  - Fetch delta from external API
  - Create `RawEvent` rows (one per new message/event)
  - Returns cursor for next poll

**Message (Normalized Event):**
- Purpose: Canonical email representation (deduplicated across sources)
- File: `packages/core/src/core/db/models.py` line 60
- Pattern:
  - Unique on (user_id, dedup_hash)
  - Stores sender, title, body_preview, body_full, message_ts
  - Extra JSON for source-specific data (labels, is_canvas)
  - Linked to source via raw_event_id

**ActionItem (Extracted Task):**
- Purpose: A task/todo extracted from a message or created manually
- File: `packages/core/src/core/db/models.py` line 136
- Pattern:
  - Status: "proposed" (suggested), "active" (user accepted), "done", "dismissed"
  - due_at, priority, confidence scored by LLM
  - Linked to message_id (can be null for manual tasks)

**Reminder (Scheduled Notification):**
- Purpose: A point-in-time alert for an ActionItem
- File: `packages/core/src/core/db/models.py` line 152
- Pattern:
  - Unique on (action_item_id, remind_at, channel)
  - Status: "pending", "sent"
  - Created at cadence-driven intervals (gentle/standard/aggressive)
  - Sent via channel (Telegram, CLI, etc.)

**Policy (Adaptive Rules):**
- Purpose: Per-day settings driven by PVI score (workload index)
- File: `packages/core/src/core/db/models.py` line 197
- Pattern:
  - Unique on (user_id, date)
  - Regime: "overloaded", "peak", "normal", "recovery"
  - Controls: max_digest_items, escalation_level, reminder_cadence, auto_activate
  - Computed daily at 7am based on PVIDailyScore

**MessageSummary (LLM Extraction Output):**
- Purpose: Store LLM-generated summary, urgency, labels, and validation status
- File: `packages/core/src/core/db/models.py` line 81
- Pattern:
  - Unique on (message_id, prompt_version)
  - summary_short, summary_long, urgency (float 0-1)
  - extraction_failed flag for retry logic
  - Linked to LLMRun audit row

## Entry Points

**CLI (`claw` command):**
- Location: `packages/cli/src/cli/main.py`
- Triggers: User-facing commands (sync, inbox, tasks, digest, pvi, bot, worker, reply, focus, init)
- Responsibilities:
  - Setup/auth (`claw init`, `claw connect gmail/outlook/gcal`)
  - Sync (`claw sync`) — triggers normalizer manually
  - Manual digest/PVI view
  - Telegram bot launch (`claw bot start`)
  - Background worker start (`claw worker start`)
  - Task/reply management

**Worker (Background Scheduler):**
- Location: `apps/worker/src/worker/main.py`
- Triggers: APScheduler cron/interval jobs (runs continuously in background)
- Responsibilities:
  - Polling (Gmail, Outlook, GCal)
  - Normalization
  - LLM extraction
  - Reminder scheduling & dispatch
  - Daily PVI/digest computation
  - Heartbeat monitoring

**API (Web Dashboard):**
- Location: `apps/api/src/api/main.py`
- Triggers: HTTP GET/POST requests to FastAPI routes
- Responsibilities:
  - Serve HTML dashboard (`/`, `/tasks`, `/inbox`)
  - JSON API endpoints (`/api/tasks`, `/api/messages`, `/api/pvi/today`)
  - Task state mutations (accept/dismiss)
  - Markdown email replies

**Telegram Bot (Interactive):**
- Location: `apps/bot/src/bot/main.py`
- Triggers: Telegram messages (long-polling)
- Responsibilities:
  - View tasks/inbox/digest/PVI
  - Create new tasks (`/newtask`)
  - Accept/dismiss task suggestions (inline buttons)
  - View/send email replies (`/reply`)
  - Focus mode management

## Error Handling

**Strategy:** Fail-soft with alerts; circuit breaker for cascading LLM failures; retry on transient errors.

**Patterns:**

- **Connector Errors (Auth, API Failures):**
  - Catch `RuntimeError` ("not connected", "auth", "credentials")
  - Alert user: "Gmail auth expired. Run: `claw connect gmail`"
  - Continue to next source (don't crash entire poll)
  - File: `apps/worker/src/worker/jobs.py` lines 42-51

- **LLM Extraction Failures:**
  - Catch invalid JSON: retry once with full response dump
  - Catch validation error (Pydantic): log, mark `extraction_failed=True`, move to next message
  - If 5 consecutive failures across all messages: **open circuit breaker**
  - Breaker pauses extraction for 10 minutes, alerts user
  - File: `packages/core/src/core/llm/extractor.py`, `apps/worker/src/worker/jobs.py` lines 54-86

- **Database Errors:**
  - `IntegrityError` on Reminder creation: ignore (already scheduled)
  - All transaction errors: rollback, log, alert
  - File: `packages/core/src/core/pipeline/reminders.py` lines 53-58

- **Telegram Notification Failures:**
  - Try/except with `return False` (fail-soft)
  - Don't crash reminder dispatch on network hiccup
  - File: `packages/core/src/core/telegram_notify.py`, `packages/core/src/core/telegram_client.py`

## Cross-Cutting Concerns

**Logging:**
- Framework: `structlog` (structured JSON logging)
- Pattern: `log.info("event_name", key=value, ...)` for observability
- Files: All modules use `log = structlog.get_logger()` at top

**Validation:**
- Framework: Pydantic (strict mode, `extra=forbid`)
- Pattern: `ExtractionResult` schema enforces LLM output shape
- File: `packages/core/src/core/schemas/llm.py`

**Authentication:**
- OAuth2 for Gmail (`gmail_credentials.json`)
- MSAL for Outlook (device code flow, tenant = "organizations" for NUS)
- API Key for web dashboard (`dashboard_api_key` env var, gated in `api/auth.py`)
- Files: `packages/connectors/src/connectors/gmail/auth.py`, `packages/connectors/src/connectors/outlook/auth.py`

**Configuration:**
- Singleton pattern: `get_settings()` reads `.env` once, cached globally
- File: `packages/core/src/core/config.py` (resolved from project root)
- LLM provider selection: `llm_provider = "gemini"` or `"anthropic"`

**Time Handling:**
- All timestamps: timezone-aware UTC (`datetime.now(tz=timezone.utc)`)
- User timezone for display: `user_timezone` config (default "Asia/Singapore")
- Cron jobs (daily digest): 7am in UTC, displayed in user timezone
- File: Consistent across `packages/core/src/core/pipeline/*`, `packages/core/src/core/pvi/*`

**Multi-User Support:**
- Default user: `default_user_id` env var (filled during `claw init`)
- Each Source, Message, ActionItem, Reminder scoped to user_id
- API/Bot default to `default_user_id`, but query filters by user_id
- Files: `packages/core/src/core/config.py`, all models in `packages/core/src/core/db/models.py`

---

*Architecture analysis: 2026-03-19*
