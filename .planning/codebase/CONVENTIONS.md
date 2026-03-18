# Coding Conventions

**Analysis Date:** 2026-03-19

## Naming Patterns

**Files:**
- Modules: `snake_case.py` (e.g., `circuit_breaker.py`, `telegram_notify.py`)
- Classes: PascalCase within modules (e.g., `CircuitBreaker`, `Settings`, `User`)
- Private functions: `_snake_case` prefix (e.g., `_uuid()`, `_features()`, `_make_settings()`)
- Test helpers: `_helper_name()` convention (e.g., `_canvas()`, `_make_settings()`)
- Test files: `test_<feature>.py` (e.g., `test_circuit_breaker.py`, `test_pvi.py`)

**Functions:**
- Public functions: `verb_noun_snake_case()` (e.g., `record_failure()`, `get_settings()`, `send_task_notification()`)
- Async-aware: same convention, no `async_` prefix (e.g., `poll_gmail()`, `extract_all_pending()`)
- Boolean returning: `is_<predicate>()` or `<verb>_<noun>()` (e.g., `is_open()`, `record_success()`)

**Variables:**
- Local: `snake_case` (e.g., `history_id`, `mock_item`, `gmail_pairs`)
- Module-level constants: `SCREAMING_SNAKE_CASE` (e.g., `POLICY_MAP`, `SCOPES`)
- Private module state: `_leading_underscore` (e.g., `_settings`, `_engine`, `_last_alert`)
- SQLAlchemy columns: `snake_case` matching database columns (e.g., `source_type`, `body_full`, `sync_cursor`)

**Types:**
- Use Python 3.10+ union syntax: `str | None` not `Optional[str]`
- Literal types: `Literal["recovery", "normal", "peak"]`
- Type hints on function signatures (required for public APIs)
- Use pydantic Field() for config: `field_name: str = Field(default="value")`

**Pydantic Models:**
- Settings: `BaseSettings` subclass with `SettingsConfigDict`
- Data validation: use `Field()` with defaults, descriptions optional
- Config: `.env` environment variable resolution via `SettingsConfigDict(env_file=...)`

## Code Style

**Formatting:**
- Line length: 100 characters (configured in `pyproject.toml` `[tool.ruff] line-length = 100`)
- Ruff is the linter/formatter
- No explicit formatting tool beyond ruff (black/autopep8 not used)

**Linting:**
- Tool: Ruff
- Key settings: line-length = 100
- Configuration: `pyproject.toml` `[tool.ruff]` section
- No separate `.pylintrc` or `.flake8` configs

**Indentation:**
- 4 spaces (Python standard)
- SQLAlchemy model definitions: column definitions unindented within class body

## Import Organization

**Order:**
1. Future imports (`from __future__ import annotations`)
2. Standard library (`import os`, `from datetime import datetime`)
3. Third-party (`import sqlalchemy`, `import pydantic`, `from typing import ...`)
4. Local application (`from core.config import ...`, `from connectors.gmail import ...`)
5. Type-checking only imports (`from typing import TYPE_CHECKING`)

**Path Aliases:**
- No path aliases configured
- Absolute imports from package roots (e.g., `from core.config import get_settings`, `from connectors.gmail.poller import poll_gmail`)
- Full module paths preserved (no shortened imports)

**Lazy Imports in CLI:**
- CLI command functions use lazy imports inside function bodies to avoid circular dependencies
- Example in `sync.py`: imports happen inside `cmd_sync()`, not at module level
- Pattern: `from connectors.gmail.poller import poll_gmail` inside the function

**Type Checking Imports:**
- Pattern observed: `from __future__ import annotations` at top of file
- TYPE_CHECKING blocks used when needed: `if TYPE_CHECKING: from some.module import Type`

## Error Handling

**Patterns:**
- **Fail-soft convention:** Notification functions always catch exceptions and return `bool` (True on success, False on failure)
  - Never raise exceptions to caller
  - Log errors via structlog
  - Example: `telegram_notify.py` catches `Exception`, logs, returns `False`

- **Context managers for resources:**
  - Database access: `with get_db() as db:` ensures auto-commit on success, rollback on exception
  - Example: `engine.py` get_db() yields session, auto-commits if no exception

- **Health alerts:**
  - Critical errors trigger `alert(key, message, level)` for Telegram notification
  - Rate-limited by key with cooldown window
  - Example: `health.py` alert() wraps exceptions, returns None

- **Circuit breaker pattern:**
  - `CircuitBreaker` class tracks failures, opens after threshold, auto-resets after window
  - Used to protect LLM API calls in jobs
  - Record failures/successes via `record_failure()` / `record_success()`

- **Dataclass validation:**
  - Pydantic handles validation on model instantiation
  - No explicit try/except for validation errors — let them propagate at config load time

## Logging

**Framework:** structlog

**Configuration:**
- `configure_logging(level: str = "INFO")` in `logging.py`
- Processors: merge_contextvars, add_log_level, TimeStamper (ISO format), JSONRenderer
- Output: PrintLoggerFactory (to stdout/stderr)

**Patterns:**
- Get logger: `log = structlog.get_logger()` at module level
- Log with context: `log.warning("circuit_breaker_tripped", name=self.name, failures=self._failures)`
- Levels: `.debug()`, `.info()`, `.warning()`, `.error()`
- Key pattern: `event_name`, then keyword arguments for context
- Example: `log.info("circuit_breaker_reset", name=self.name)`

**Usage Guidelines:**
- Log on state transitions (circuit breaker trip, alert sent, health check)
- Log on skipped operations (task notification priority check, alert rate-limited)
- Log on errors (with exception message as string, not traceback)
- Don't log secrets or sensitive data

## Comments

**When to Comment:**
- Document complex algorithms or non-obvious logic (e.g., circuit breaker reset window math)
- Explain WHY, not WHAT (code shows WHAT)
- Reference external resources when relevant (e.g., Gmail History API, Microsoft Graph endpoint)

**Doc Style:**
- Module docstrings: triple-quoted, explain purpose and key patterns
- Example: `circuit_breaker.py` has module docstring with usage example
- Example: `gmail/poller.py` has docstring explaining History API delta sync strategy

**Function Docstrings:**
- Used on public API functions
- Format: one-line summary, blank line, detailed description if needed
- Args/Returns documented in docstring or via type hints
- Example: `send_task_notification()` has detailed Args and return value docstring

**Inline Comments:**
- Sparse but present where algorithm intent is non-obvious
- Example: comments in circuit breaker on auto-reset timing logic
- Example: comments in dedup hash explaining stable hash requirement

## Function Design

**Size:** Functions typically 10-50 lines. Longer functions broken into private helpers.
- Example: `poll_gmail()` ~60 lines, uses `_with_backoff()`, `_fetch_message_ids_delta()` helpers
- Example: `send_task_notification()` ~25 lines, single responsibility

**Parameters:**
- Named parameters preferred
- Use `|` union types (Python 3.10+)
- Optional parameters have defaults
- Pattern: required first, optional last

**Return Values:**
- Explicit return types in signature (e.g., `-> bool`, `-> tuple[list[str], str]`)
- Boolean return on success/failure for side-effect functions
- None for setters/alerts
- Tuples for multiple returns (e.g., extraction results `(success_count, failed_count)`)

**Private Implementation:**
- Private functions use `_` prefix and are not exported
- Kept in same module as public caller (not in separate files)
- Example: `_with_backoff()`, `_extract_message_fields()`, `_uuid()`

## Module Design

**Exports:**
- Public functions/classes exported at module level
- No `__all__` explicitly defined (implicit via no `_` prefix)
- Modules organized by responsibility (auth, poller, models, etc.)

**Barrel Files:**
- Minimal use of `__init__.py` re-exports
- Package `__init__.py` files typically empty or import for convenience
- Example: `packages/connectors/src/connectors/__init__.py` empty

**Organization:**
- `core/` — database, logging, config, shared utilities
- `connectors/` — provider-specific integrations (gmail, outlook, gcal, canvas)
- `cli/` — command-line commands organized by feature
- `api/` — FastAPI routes and web handlers
- `worker/` — background job scheduler and job definitions

## Async Patterns

**None in codebase** — pure synchronous Python (asyncio_mode = "auto" in pytest.ini for async test support, but no async code present)

## String Formatting

**Style:**
- f-strings exclusively (Python 3.6+)
- Markdown formatting with escape for special chars when needed
- Example: `f"📋 *New task*\n{title}\n"` (Unicode emojis, no escape needed)
- Telegram MarkdownV2: use `escape_markdown(text, version=2)` when accepting user input

## Type Hints

**Required:**
- Public function signatures must have type hints
- Return type always specified
- Private functions encouraged but not required

**Patterns:**
- `str | None` union syntax
- `list[dict]`, `dict[str, Any]`
- Literal types for constrained strings
- `datetime | None` for optional timestamps
- `Generator[Session, None, None]` for context managers

## Configuration

**Pattern:**
- Singleton `Settings` class in `core/config.py`
- Access via `get_settings()` function (lazy initialization)
- All settings from environment via Pydantic `SettingsConfigDict`
- Default values hardcoded in Settings (not in .env)
- .env file optional for local development

**Usage:**
- Never pass settings as function parameter (use dependency injection via `get_settings()`)
- Settings resolved at module import time, cached in `_settings` global

---

*Convention analysis: 2026-03-19*
