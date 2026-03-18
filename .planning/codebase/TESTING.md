# Testing Patterns

**Analysis Date:** 2026-03-19

## Test Framework

**Runner:**
- pytest (installed via pyproject.toml)
- Configuration: `pytest.ini` in project root

**Asyncio Support:**
- Mode: auto (asyncio_mode = "auto" in both `pytest.ini` and `pyproject.toml`)
- No async code in codebase (but framework ready)

**Run Commands:**
```bash
python3 -m pytest tests/unit/ -v              # Run all unit tests with verbose output
python3 -m pytest tests/unit/ -v --tb=short   # Run with short traceback format
python3 -m pytest tests/ -v                   # Run all tests (unit + integration)
python3 -m pytest tests/unit/test_circuit_breaker.py -v  # Single file
```

## Test Organization

**Location:**
- `tests/unit/` — unit tests (no external dependencies, in-memory only)
- `tests/integration/` — integration tests (require live database, marked with @pytest.mark.integration)
- `tests/conftest.py` — shared pytest configuration and markers

**Directory Structure:**
```
tests/
├── conftest.py                    # Shared test config, custom markers
├── unit/
│   ├── __init__.py               # Empty
│   ├── test_circuit_breaker.py
│   ├── test_pvi.py
│   ├── test_telegram_notify.py
│   ├── test_canvas_notify.py
│   ├── test_dashboard_api.py
│   ├── test_dedup.py
│   ├── test_outlook_poller.py
│   ├── test_init_command.py
│   ├── test_focus_mode.py
│   ├── test_meeting_prep.py
│   ├── test_normalizer_multisource.py
│   ├── test_canvas_parser.py
│   ├── test_telegram_client.py
│   ├── test_bot_callbacks.py
│   ├── test_dashboard_auth.py
│   └── [27 test files total]
└── integration/
    └── conftest.py               # Integration-specific fixtures
```

**Test File Naming:**
- Pattern: `test_<feature>.py`
- Maps to feature being tested (e.g., `test_circuit_breaker.py` tests CircuitBreaker class)

## Test Structure

**Basic Pattern:**
```python
# tests/unit/test_circuit_breaker.py
"""Unit tests for CircuitBreaker — no external deps."""
from datetime import datetime, timezone, timedelta
import pytest

from core.circuit_breaker import CircuitBreaker


def test_breaker_starts_closed():
    cb = CircuitBreaker("test")
    assert not cb.is_open()


def test_breaker_opens_at_threshold():
    cb = CircuitBreaker("test", threshold=3)
    cb.record_failure()
    cb.record_failure()
    assert not cb.is_open()
    cb.record_failure()
    assert cb.is_open()
```

**Patterns:**
- **Setup:** Direct instantiation (no fixtures for simple cases)
- **Teardown:** None needed (in-memory objects garbage collected)
- **Assertion:** Direct `assert` statements
- **Per-test isolation:** Each test creates fresh objects, no shared state (except module singletons)

**Helper Functions:**
- Private test helpers with `_` prefix
- Created at module level in test file
- Example in `test_telegram_notify.py`:
  ```python
  def _make_settings(enabled=True, min_priority=60):
      s = MagicMock()
      s.telegram_enabled = enabled
      s.bot_notify_min_priority = min_priority
      return s
  ```
- Example in `test_pvi.py`:
  ```python
  def _features(**kwargs):
      base = {"tasks_open": 0, "tasks_overdue": 0,
              "inbox_unread": 0, "incoming_24h": 0, "calendar_minutes": 0}
      base.update(kwargs)
      return base
  ```

## Mocking

**Framework:** unittest.mock (standard library)

**Patterns:**
```python
from unittest.mock import patch, MagicMock

# Pattern 1: Patch and patch context manager
with patch("core.telegram_notify.get_settings",
           return_value=_make_settings()), \
     patch("core.telegram_notify.send_message_with_keyboard",
           return_value=True) as mock_send:
    from core.telegram_notify import send_task_notification
    result = send_task_notification(...)
    mock_send.assert_called_once()

# Pattern 2: MagicMock for object creation
mock_db = MagicMock()
mock_db.__enter__ = lambda s: mock_db
mock_db.__exit__ = MagicMock(return_value=False)
mock_db.query.return_value.filter.return_value.first.return_value = None

# Pattern 3: Verify call arguments
call_args = mock_send.call_args
text = call_args[0][0]  # First positional argument
keyboard = call_args[0][1]  # Second positional argument
assert "Task title" in text
```

**What to Mock:**
- External service calls (Telegram, Gmail API, Outlook Graph)
- Database operations (get_db context manager, query chains)
- Configuration reads (get_settings())
- Time-based operations (datetime.now() when testing timeouts)

**What NOT to Mock:**
- Core business logic classes (CircuitBreaker, PVI scoring, dedup hash)
- In-memory utilities
- SQLAlchemy model construction (mock the session/query result instead)
- Pydantic models (instantiate real models with test data)

**MagicMock Common Patterns:**
- `mock.return_value = value` — return value on call
- `mock.side_effect = Exception()` — raise exception on call
- `mock.assert_called_once()` — verify called exactly once
- `mock.assert_called_once_with(*args, **kwargs)` — verify call signature
- `mock.assert_not_called()` — verify not called
- `mock.call_args[0]` — tuple of positional arguments
- `mock.call_args[1]` — dict of keyword arguments
- `mock.__enter__ = lambda s: mock` — make MagicMock a context manager

## Test Data & Fixtures

**Test Data Pattern:**
```python
# Simple dictionaries for API responses
graph_msg = {
    "id": "AAMk123",
    "subject": "Assignment due Friday",
    "from": {"emailAddress": {"address": "prof@nus.edu.sg", "name": "Prof Tan"}},
    "receivedDateTime": "2026-03-02T10:00:00Z",
    "bodyPreview": "Please submit by 11:59pm",
}

# Builder pattern for complex objects
def _canvas(canvas_type="assignment", course_code="CS3230", ...):
    return CanvasParseResult(
        is_canvas=True,
        course_code=course_code,
        ...
    )
```

**Fixtures:**
- Pytest fixtures not heavily used (simple cases use direct instantiation)
- Custom markers available: `@pytest.mark.integration` for database-dependent tests
- Conftest.py registers markers via `config.addinivalue_line("markers", ...)`

**No Factories:**
- Simple test helper functions used instead of factory libraries
- Dataclass-like builders for complex test objects

## Coverage

**Requirements:** No enforced minimum coverage target

**Current Status:**
- 135 unit tests passing (all green)
- Coverage tracking possible via: `pytest --cov=core --cov=connectors --cov=apps`

## Test Types

**Unit Tests:**
- Scope: Single function/class, no I/O
- Location: `tests/unit/`
- Examples:
  - `test_circuit_breaker.py` — CircuitBreaker state machine
  - `test_dedup.py` — hash stability, no I/O
  - `test_pvi.py` — PVI scoring algorithm, pure functions
  - `test_canvas_parser.py` — string parsing, no I/O

**Integration Tests:**
- Scope: Multiple components, requires live PostgreSQL
- Location: `tests/integration/`
- Marker: `@pytest.mark.integration`
- Example commands: Tests would use real database, config, connectors
- **Not included in standard test run** (`pytest tests/unit/` skips integration tests)

**E2E Tests:**
- Status: Not present
- Could be added for Telegram bot interactions, but currently not implemented

## Common Test Patterns

**Testing Boolean Returns (Success/Failure):**
```python
def test_send_task_notification_high_priority_sends():
    """Priority >= threshold → sends keyboard message."""
    with patch("core.telegram_notify.get_settings",
               return_value=_make_settings(min_priority=60)), \
         patch("core.telegram_notify.send_message_with_keyboard",
               return_value=True) as mock_send:
        from core.telegram_notify import send_task_notification
        result = send_task_notification(
            task_id="abc-123",
            title="Submit CS3230 problem set",
            priority=85,
            due_at=None,
        )

    assert result is True
    mock_send.assert_called_once()
```

**Testing State Transitions:**
```python
def test_breaker_opens_at_threshold():
    cb = CircuitBreaker("test", threshold=3)
    cb.record_failure()
    cb.record_failure()
    assert not cb.is_open()  # still below threshold
    cb.record_failure()
    assert cb.is_open()  # now open
```

**Testing Conditional Logic with Time:**
```python
def test_breaker_auto_resets_after_timeout():
    cb = CircuitBreaker("test", threshold=2, reset_minutes=10)
    cb.record_failure()
    cb.record_failure()
    assert cb.is_open()
    # Simulate the reset window having elapsed
    cb._tripped_at = datetime.now(timezone.utc) - timedelta(minutes=11)
    assert not cb.is_open()
    assert cb._failures == 0
```

**Testing Error Conditions:**
```python
def test_send_task_notification_disabled_skips():
    """telegram_enabled=False → returns False."""
    with patch("core.telegram_notify.get_settings",
               return_value=_make_settings(enabled=False)), \
         patch("core.telegram_notify.send_message_with_keyboard") as mock_send:
        from core.telegram_notify import send_task_notification
        result = send_task_notification("abc", "Task", priority=90)

    assert result is False
    mock_send.assert_not_called()
```

**Testing Message Content/Format:**
```python
def test_canvas_notification_assignment_plain():
    """Canvas without URL → uses send_message, text contains course + title + due."""
    with patch("core.canvas_notify.get_settings", return_value=_make_settings()), \
         patch("core.canvas_notify.send_message", return_value=True) as mock_send:
        result = send_canvas_notification(_canvas(), "msg-1")

    assert result is True
    mock_send.assert_called_once()
    text = mock_send.call_args[0][0]
    assert "CS3230" in text
    assert "Problem Set 4" in text
```

**Testing Data Transformations:**
```python
def test_extract_message_fields_basic():
    graph_msg = {
        "id": "AAMk123",
        "subject": "Assignment due Friday",
        "from": {"emailAddress": {"address": "prof@nus.edu.sg", "name": "Prof Tan"}},
        ...
    }
    fields = _extract_message_fields(graph_msg)
    assert fields["external_id"] == "AAMk123"
    assert fields["sender"] == "prof@nus.edu.sg"
    assert fields["title"] == "Assignment due Friday"
```

**Testing Complex Mock Chains:**
```python
def test_get_tasks_returns_list():
    mock_item = MagicMock()
    mock_item.id = "task-uuid-1"
    mock_item.title = "Reply to Prof Chen"

    mock_db = MagicMock()
    mock_db.__enter__ = lambda s: mock_db
    mock_db.__exit__ = MagicMock(return_value=False)
    # Chain: db.query().filter().order_by().limit().all()
    mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [mock_item]

    with patch("core.db.engine.get_db", return_value=mock_db):
        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        resp = client.get("/api/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["title"] == "Reply to Prof Chen"
```

## Test Execution Context

**PYTHONPATH:**
- Set in test environment: `packages/core/src:packages/connectors/src:packages/cli/src:apps/bot/src:apps/api/src`
- Allows absolute imports from package roots (e.g., `from core.config import get_settings`)

**Module-Level Imports:**
- Many tests do `from core.telegram_notify import send_task_notification` INSIDE the test function
- Reason: Patches are applied before import, ensuring mocked versions are loaded
- Pattern allows same test file to patch different modules in different tests

**Path Setup in Some Tests:**
```python
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../packages/core/src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../apps/api/src'))
```
- Used in `test_dashboard_api.py` for FastAPI TestClient setup
- Ensures relative imports resolve correctly from test file location

## Test Isolation

**No Shared State Between Tests:**
- Each test creates fresh object instances
- Mocks reset between tests (new patch context per test)
- Module singletons (e.g., `_settings` in config.py) isolated via patching
- In-memory CircuitBreaker state reset via `reset_alerts()` if needed in integration tests

**Database Isolation:**
- Unit tests: mock `get_db()`, never hit real database
- Integration tests: would use isolated test database (not implemented)

## Coverage Targets

**Current:** No explicit targets enforced

**Running Coverage:**
```bash
pytest tests/unit/ --cov=core --cov=connectors --cov=apps --cov-report=term-missing
```

---

*Testing analysis: 2026-03-19*
