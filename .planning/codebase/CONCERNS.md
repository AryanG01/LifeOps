# Codebase Concerns

**Analysis Date:** 2026-03-19

## Tech Debt

**In-Memory State Loss on Restart:**
- Issue: Circuit breaker (`CircuitBreaker` class), rate-limit state (`_last_alert` dict), and poll tracking (`_last_poll` dict) all stored in process memory. Worker restart clears all state.
- Files: `packages/core/src/core/circuit_breaker.py`, `packages/core/src/core/health.py`, `apps/worker/src/worker/jobs.py` (line 23)
- Impact:
  - Circuit breaker resets on worker restart, potentially resuming failed LLM calls immediately
  - Health alerts can repeat within cooldown window if worker crashes
  - Poll heartbeat can miss stale source detection if worker restarts
- Fix approach: Persist state to Redis or PostgreSQL. Move `CircuitBreaker` state, `_last_alert` timestamps, and `_last_poll` tracking into database with expiration TTLs. Use pessimistic locking if multiple workers run.

**N+1 Query Patterns:**
- Issue: Multiple `.all()` followed by iteration. Examples: `digest/generator.py` line 39, 46, 48-57; `pvi/engine.py` line 33-46; `pipeline/reminders.py` line 96-98, 103.
- Files: `packages/core/src/core/digest/generator.py`, `packages/core/src/core/pvi/engine.py`, `packages/core/src/core/pipeline/reminders.py`, `packages/core/src/core/calendar/prep.py`
- Impact: Scale degrades with large datasets. Daily digest generation can issue dozens of queries for 1000+ pending tasks.
- Fix approach: Use SQLAlchemy joins and eager loading. Replace `.all()` chains with explicit `.join()` statements. Add indexes on `(user_id, status, due_at)` to minimize full table scans.

**Message Body Truncation Without Warning:**
- Issue: `body_full` silently truncated to 10,000 chars in two places without user notification.
- Files: `packages/connectors/src/connectors/gmail/poller.py` (line 134), `packages/connectors/src/connectors/outlook/poller.py` (line 55)
- Impact: Long messages (contracts, detailed reports) lose critical content during extraction. User unaware of loss.
- Fix approach: Store full message length in `extra_json`. Add warning log at INFO level when truncation occurs. Consider raising body limit to 50k or implement chunking strategy.

**Markdown Injection in Telegram Alerts:**
- Issue: `alert()` function directly interpolates message into MarkdownV2 format without escaping special characters.
- Files: `packages/core/src/core/health.py` (line 47)
- Impact: Error messages containing underscore, backtick, or asterisk will break Telegram formatting or be interpreted as markup. Low severity but silent failure.
- Fix approach: Use `escape_markdown(message, version=2)` from `telegram` or `python-telegram-bot` library on all user-facing text before format string interpolation.

**Hardcoded Default User ID:**
- Issue: Single default user UUID hardcoded: `00000000-0000-0000-0000-000000000001`.
- Files: `packages/core/src/core/config.py` (line 42), `apps/worker/src/worker/jobs.py` (line 158)
- Impact: Multi-user support via email login exists, but background jobs (meeting prep) hardcode one user. New user's calendar events will not trigger meeting prep.
- Fix approach: Refactor `job_meeting_prep()` to iterate over all users like `job_daily_pvi_and_digest()` does. Remove `default_user_id` special case or reserve only for CLI commands.

---

## Known Bugs

**Silent RawEvent Duplicate Handling:**
- Symptoms: Duplicate Gmail messages detected by unique constraint (`external_id + source_id`) silently committed to database.
- Files: `packages/connectors/src/connectors/gmail/poller.py` (line 146-150)
- Trigger: Run `claw poll` twice on same interval before processing completes.
- Issue: Exception caught but not re-raised; function returns `False` without explicit error logging. Caller does not know insertion failed.
- Fix approach: Explicitly check for `IntegrityError` (unique violation) vs other exceptions. Log uniqueness failures at DEBUG level, other failures at ERROR. Return structured result (success/skipped/failed) instead of bool.

**API Key Auth Disabled Silently:**
- Symptoms: Dashboard API unprotected when `dashboard_api_key=""` in config. No warning to user.
- Files: `apps/api/src/api/auth.py` (line 15-16)
- Trigger: Deploy without setting `dashboard_api_key` env var.
- Issue: Auth mechanism silently disables instead of failing loudly. Operator unaware their dashboard is public.
- Fix approach: Check at startup: `if not dashboard_api_key and not os.getenv("SKIP_API_AUTH"): raise ValueError(...)`. Log at WARNING level during init.

**Outlook Tenant Default "common" Has Known Issues:**
- Symptoms: AADSTS50059 errors when using tenant="common" with NUS Outlook account.
- Files: `packages/core/src/core/config.py` (line 52)
- Workaround: Set `OUTLOOK_TENANT=organizations` (documented in MEMORY.md).
- Issue: Default remains "common" despite known breakage. New deployments will fail Outlook setup without explicit config change.
- Fix approach: Change default to "organizations" OR add validation on startup to check for multi-tenant orgs and warn if using "common".

---

## Security Considerations

**Telegram Bot Token Exposed in Error Logs:**
- Risk: If Graph API or httpx calls fail, token could appear in exception traceback.
- Files: `packages/connectors/src/connectors/outlook/poller.py` (line 86), potentially others using httpx with Bearer auth.
- Mitigation: Exception is caught and logged at ERROR level. Token never explicitly logged.
- Recommendation: Add blanking filter to structlog: redact `Authorization` headers in HTTP error logging. Test with deliberate auth failure.

**API Key Comparison Uses Direct ==:**
- Risk: String comparison vulnerable to timing attacks (negligible in practice for single-user system).
- Files: `apps/api/src/api/auth.py` (line 18)
- Mitigation: Single-user system; attacker must be on same machine to measure timing. API key stored in .env (not git).
- Recommendation: Use `hmac.compare_digest()` for constant-time comparison. Not critical but defensive.

**Gmail Credentials Stored as JSON File:**
- Risk: `~/.config/clawdbot/gmail_credentials.json` world-readable on multi-user systems.
- Files: `packages/core/src/core/config.py` (line 56-57); actual storage in `packages/connectors/src/connectors/gmail/auth.py`
- Mitigation: File permissions depend on system umask. No explicit 0600 chmod applied.
- Recommendation: After credential write, explicitly set permissions: `os.chmod(path, 0o600)` in `gmail/auth.py`.

**Database URL in Config Allows Plaintext Passwords:**
- Risk: `DATABASE_URL` may contain password. Visible in process env via `ps aux`.
- Files: `packages/core/src/core/config.py` (line 14-15)
- Mitigation: PostgreSQL defaults to MD5 hashing. .env file is in .gitignore.
- Recommendation: Use PG connection services file (`~/.pgpass`) or environment variables parsed separately. Consider rotating default password after first run.

---

## Performance Bottlenecks

**LLM Extraction Retries Without Backoff:**
- Problem: Failed extraction retries immediately (attempt 2) with no delay. If rate-limited, both attempts fail.
- Files: `packages/core/src/core/llm/extractor.py` (line 273-300)
- Cause: No exponential backoff between retries. Circuit breaker only trips after 5 failures.
- Improvement path: Add `time.sleep(2**attempt)` between retries. Lower circuit breaker threshold to 3 if using Gemini free tier (10 RPM limit).

**Digest Generation Loads Full Message Objects:**
- Problem: `digest/generator.py` joins Message + MessageSummary, loads all fields for 15+ items per day.
- Files: `packages/core/src/core/digest/generator.py` (line 48-57)
- Cause: `join()` with `.all()` loads full Message rows despite needing only (sender, subject, summary_short).
- Improvement path: Use `.values("message_id", "sender", "title", "summary_short")` instead of loading ORM objects. Avoid full Message load.

**Poll History Pagination Not Batched:**
- Problem: Gmail history.list pagination fetches messages one at a time in nested loop.
- Files: `packages/connectors/src/connectors/gmail/poller.py` (line 77-87, 109-150)
- Cause: Inner loop calls `_fetch_and_store_message()` per msg_id; each call makes separate API request.
- Improvement path: Batch fetch: collect 50 message IDs per pagination result, then call `messages.batchGet()` once.

**PVI Computation Queries Entire Task Table:**
- Problem: `compute_pvi_daily()` queries all open tasks for one user on every daily run.
- Files: `packages/core/src/core/pvi/engine.py` (line 33-46)
- Cause: No date-based partitioning. Assumes small task volume.
- Improvement path: Add index on `(user_id, status, created_at)`. Use `.filter(ActionItem.created_at >= today - 30 days)` to limit scope.

---

## Fragile Areas

**Canvas Email Detection Regex-Based, Not Robust:**
- Files: `packages/connectors/src/connectors/canvas/parser.py` (line 14-47)
- Why fragile: Patterns match any NUS-affiliated sender + canvas keyword. False positives on newsletters from ntu.edu.sg or canvas-related support emails.
- Safe modification:
  1. Add explicit Canvas URL validation: require at least one CANVAS_URL_RE match before marking `is_canvas=True`.
  2. Add integration test with real Canvas emails from canvas.nus.edu.sg.
  3. Consider allowlist of known Canvas instructors instead of broad patterns.
- Test coverage: `tests/unit/test_canvas_parser.py` exists; add case for false-positive scenarios (ntu.edu.sg, no URL, generic "canvas" mention).

**Extraction Failure Handling Uses Generic `Exception`:**
- Files: `packages/core/src/core/llm/extractor.py` (line 287-300, 325, 377, 399)
- Why fragile: Catches all exceptions including `KeyboardInterrupt`, `SystemExit`. Broad except masks bugs.
- Safe modification: Replace `except Exception as exc:` with specific catches:
  - `json.JSONDecodeError` → mark as validation failure
  - `anthropic.APIError` / `openai.APIError` → trigger circuit breaker
  - Others → re-raise or log at CRITICAL
- Test coverage: Add unit tests for each exception type to verify correct handling.

**Deduplication Hash Uses Simple String Concatenation:**
- Files: `packages/core/src/core/pipeline/normalizer.py` (line 17-20)
- Why fragile: Hash key `f"{user_id}:{external_id}:{sender}:{subject}"` assumes all fields immutable. If sender parsing changes or API returns different format, duplicates reappear.
- Safe modification:
  1. Document that this hash is stable API contract.
  2. Add versioning: `f"v1:{user_id}:..."` to allow hash evolution.
  3. Add database migration to backfill existing hashes if format changes.
  4. Test: ensure same hash produced for same input across code changes.

**Raw Message Body Parsing Splits on First Newline:**
- Files: `packages/core/src/core/llm/extractor.py` (line 131-132); markdown fence stripping uses `.split("\n", 1)[-1]`
- Why fragile: If LLM includes content before fence (e.g., "Here's the JSON:\n```json\n{...}"), split fails.
- Safe modification: Use regex `r"```(?:json)?\n(.*?)\n```"` with DOTALL flag instead of string split. Add test for various fence formats.

---

## Scaling Limits

**Circuit Breaker State Not Shared Across Workers:**
- Current capacity: Single worker process. LLM breaker trip affects only that worker.
- Limit: Horizontal scaling impossible. Deploy 2 workers → both independently trigger extraction, wasting quota.
- Scaling path:
  1. Move breaker state to Redis (short TTL).
  2. Use `INCR` for failure counter, `SET ... EX` for trip timestamp.
  3. All workers check shared breaker before extraction.

**Database Connections Unmanaged in Docker Compose:**
- Current capacity: Default SQLAlchemy pool (5 connections, 10 overflow).
- Limit: 4+ simultaneous jobs can exceed connection pool. Causes connection timeouts.
- Scaling path: Set `pool_size=20, max_overflow=10` in `engine.py`. Add connection pooling middleware (pgBouncer) if running on managed DB.

**History API Delta Polling Loses State on Restart:**
- Current capacity: Single restart safe; cursor saved to DB.
- Limit: If network fails mid-fetch, `sync_cursor` partially updated. Next poll may re-fetch or miss messages.
- Scaling path: Use pessimistic locking: acquire exclusive lock on Source row during poll. Update cursor only after all messages committed.

**Telegram Message Queue Not Batched:**
- Current capacity: Each job sends Telegram messages individually (1 request per notification).
- Limit: High message volume (100 tasks) = 100 HTTP calls. Rate-limited at 30 msgs/sec = 3+ seconds latency.
- Scaling path: Implement message queue (Redis, RabbitMQ). Batch sends: max 5 msgs per second, group notifications by channel.

---

## Dependencies at Risk

**OpenAI Python Library for Gemini API:**
- Risk: Using `openai` library to call Gemini via OpenAI-compatible endpoint. If endpoint breaks or library drops compatibility, extraction fails.
- Files: `packages/core/src/core/llm/extractor.py` (line 52-71)
- Impact: LLM extraction blocked. Fallback to Anthropic only works if both keys configured.
- Migration plan: Replace with `google-generativeai` official library. Requires prompt format adjustment but more stable. Test both providers in CI.

**structlog Without Structured Output in Production:**
- Risk: structlog configured but `PrintLogRenderer` used. No central log aggregation.
- Files: Implicit in all modules; check `pyproject.toml` for structlog config.
- Impact: Logs go to stdout/stderr. Deployed on VPS/Oracle Cloud, logs lost on container restart.
- Migration plan: Add `JsonLogRenderer` to config. Ship to syslog or file. Update Docker Compose to mount `/var/log/clawdbot` volume.

**APScheduler Used But Not Distributed:**
- Risk: APScheduler in-process scheduler. Two workers = double job execution.
- Files: Implicit; check `apps/worker/src/worker/main.py` for scheduler setup.
- Impact: Digest sent twice, LLM extraction runs twice (wasting quota).
- Migration plan: Use APScheduler with SQLAlchemy store. Enable distributed lock coordination via database.

---

## Missing Critical Features

**No Retry Logic for Failed Message Normalization:**
- Problem: If `normalize_raw_event()` fails and sets `processing_error`, message never retried.
- Blocks: Tasks cannot be created from messages that had transient DB errors.
- Fix: Add job `job_retry_failed_normalizations()` that re-normalizes events with `processing_error IS NOT NULL` and `retry_count < 3`.

**No Graceful Shutdown Handling:**
- Problem: Worker jobs can be interrupted mid-run. No transaction cleanup.
- Blocks: Long-running jobs (digest generation) may leave DB locks.
- Fix: Add signal handlers for SIGTERM. Allow in-flight jobs 30-second timeout before force kill.

**No Observability for Latency:**
- Problem: LLMRun records latency_ms but no aggregation or alerts on slow runs.
- Blocks: Cannot detect degradation (API slowdown, network issues).
- Fix: Add metric aggregation: calculate p50/p95 latency per day. Alert if p95 > 5000ms.

---

## Test Coverage Gaps

**Canvas Email Parser Lacks Integration Tests:**
- What's not tested: Real Canvas emails from canvas.nus.edu.sg (only regex patterns tested).
- Files: `tests/unit/test_canvas_parser.py` (unit tests only)
- Risk: Parser may fail on live Canvas emails with unexpected HTML/encoding.
- Priority: HIGH — Canvas is NUS-specific critical path.

**Outlook Auth Device Code Flow Not Mocked:**
- What's not tested: MSAL device flow (requires manual browser interaction). Auth tests use mocks.
- Files: `tests/unit/test_outlook_auth.py` (mocked)
- Risk: Real Outlook auth may fail silently; discovered only at user setup time.
- Priority: MEDIUM — Discovered during `claw connect outlook`.

**Database Transaction Isolation Not Tested:**
- What's not tested: Concurrent writes (two jobs normalizing same message simultaneously).
- Files: No concurrent test in `test_normalizer.py`
- Risk: Unique constraint violations may not rollback properly in high-concurrency scenarios.
- Priority: MEDIUM — Low risk for single-user, but blocks horizontal scaling.

**Error Recovery Paths Not Tested:**
- What's not tested: Circuit breaker recovery (transitions from open → closed).
- Files: `tests/unit/test_circuit_breaker.py` has happy path; missing timeout/recovery scenarios.
- Risk: Breaker stuck open, LLM extraction permanently paused.
- Priority: HIGH — Critical for production resilience.

**API Dashboard SQL Injection Not Tested:**
- What's not tested: Malformed query params in dashboard API (e.g., task ID with quote).
- Files: No injection tests in `test_dashboard_api.py`
- Risk: SQLAlchemy handles escaping, but no explicit test of safety.
- Priority: LOW — SQLAlchemy ORM provides protection, but defensive test useful.

---

*Concerns audit: 2026-03-19*
