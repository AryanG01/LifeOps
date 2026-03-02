# T6 + T7: Health Alerts + Error Resilience Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the worker bulletproof — every job catches its own exceptions, fires specific Telegram alerts, and the LLM job is protected by a circuit breaker.

**Architecture:** Two new core modules (`health.py`, `circuit_breaker.py`) + wrap all 7 jobs in `try/except` in `jobs.py` + add a heartbeat job. All state in-memory (intentional — resets cleanly on worker restart). Alert deduplication via in-memory rate-limit dict.

**Tech Stack:** Python stdlib only (datetime, typing) for new modules. `unittest.mock.patch` for tests. No new dependencies.

---

## Task 1: `health.py` — Rate-Limited Alert Dispatcher

**Files:**
- Create: `packages/core/src/core/health.py`
- Create: `tests/unit/test_health.py`

**Step 1: Write the failing tests**

Create `tests/unit/test_health.py`:

```python
# tests/unit/test_health.py
"""Unit tests for health.py — mocks send_message, never hits Telegram."""
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import pytest

from core.health import alert, reset_alerts, _last_alert


@pytest.fixture(autouse=True)
def clear():
    reset_alerts()
    yield
    reset_alerts()


def test_alert_sends_on_first_call():
    with patch("core.health.send_message") as mock_send:
        alert("key1", "Something broke", level="warning")
    mock_send.assert_called_once()
    assert "⚠️" in mock_send.call_args[0][0]
    assert "Something broke" in mock_send.call_args[0][0]


def test_alert_suppresses_duplicate_within_cooldown():
    with patch("core.health.send_message") as mock_send:
        alert("key1", "First", cooldown_minutes=30)
        alert("key1", "Second", cooldown_minutes=30)
    assert mock_send.call_count == 1


def test_alert_fires_again_after_cooldown():
    with patch("core.health.send_message") as mock_send:
        _last_alert["key1"] = datetime.now(timezone.utc) - timedelta(minutes=31)
        alert("key1", "After cooldown", cooldown_minutes=30)
    mock_send.assert_called_once()


def test_alert_never_raises_when_send_fails():
    with patch("core.health.send_message", side_effect=RuntimeError("network down")):
        alert("key1", "Should not raise")  # must not raise


def test_alert_different_keys_are_independent():
    with patch("core.health.send_message") as mock_send:
        alert("key_a", "First")
        alert("key_b", "Second")
    assert mock_send.call_count == 2


def test_alert_error_level_uses_red_emoji():
    with patch("core.health.send_message") as mock_send:
        alert("key1", "Critical", level="error")
    assert "🔴" in mock_send.call_args[0][0]


def test_alert_info_level_uses_info_emoji():
    with patch("core.health.send_message") as mock_send:
        alert("key1", "FYI", level="info")
    assert "ℹ️" in mock_send.call_args[0][0]
```

**Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/unit/test_health.py -v
```
Expected: `ModuleNotFoundError: No module named 'core.health'`

**Step 3: Implement `health.py`**

Create `packages/core/src/core/health.py`:

```python
# packages/core/src/core/health.py
"""
Rate-limited Telegram health alert dispatcher.

Usage:
    from core.health import alert
    alert("gmail_auth", "Gmail auth expired. Run: claw connect gmail")

Each alert key is suppressed within its cooldown window to prevent Telegram spam.
State is in-memory — resets on worker restart (intentional).
"""
from datetime import datetime, timezone
from typing import Literal

import structlog

log = structlog.get_logger()

_last_alert: dict[str, datetime] = {}


def alert(
    key: str,
    message: str,
    level: Literal["warning", "error", "info"] = "warning",
    cooldown_minutes: int = 30,
) -> None:
    """
    Send a Telegram health alert, rate-limited by key. Never raises.

    Args:
        key: Deduplication key (e.g. "gmail_auth"). Same key suppressed within cooldown.
        message: Human-readable alert text.
        level: Emoji prefix — warning=⚠️, error=🔴, info=ℹ️.
        cooldown_minutes: Minimum minutes between alerts with the same key.
    """
    from core.telegram_client import send_message

    now = datetime.now(timezone.utc)
    last = _last_alert.get(key)
    if last is not None and (now - last).total_seconds() < cooldown_minutes * 60:
        log.debug("health_alert_suppressed", key=key)
        return

    _last_alert[key] = now
    emoji = {"warning": "⚠️", "error": "🔴", "info": "ℹ️"}.get(level, "⚠️")
    try:
        send_message(f"{emoji} *Clawdbot Alert*\n{message}")
        log.info("health_alert_sent", key=key, level=level)
    except Exception as exc:
        log.error("health_alert_failed", key=key, error=str(exc))


def reset_alerts() -> None:
    """Clear all rate-limit state. Used in tests only."""
    _last_alert.clear()
```

**Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/unit/test_health.py -v
```
Expected: 7 passed

**Step 5: Commit**

```bash
git add packages/core/src/core/health.py tests/unit/test_health.py
git commit -m "feat: add health.py — rate-limited Telegram alert dispatcher"
```

---

## Task 2: `circuit_breaker.py` — LLM Extraction Guard

**Files:**
- Create: `packages/core/src/core/circuit_breaker.py`
- Create: `tests/unit/test_circuit_breaker.py`

**Step 1: Write the failing tests**

Create `tests/unit/test_circuit_breaker.py`:

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
    assert not cb.is_open()  # still below threshold
    cb.record_failure()
    assert cb.is_open()


def test_breaker_stays_closed_below_threshold():
    cb = CircuitBreaker("test", threshold=5)
    for _ in range(4):
        cb.record_failure()
    assert not cb.is_open()


def test_record_success_resets_counter():
    cb = CircuitBreaker("test", threshold=3)
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    assert not cb.is_open()
    assert cb._failures == 0


def test_record_success_opens_tripped_circuit():
    cb = CircuitBreaker("test", threshold=2)
    cb.record_failure()
    cb.record_failure()
    assert cb.is_open()
    cb.record_success()
    assert not cb.is_open()


def test_breaker_auto_resets_after_timeout():
    cb = CircuitBreaker("test", threshold=2, reset_minutes=10)
    cb.record_failure()
    cb.record_failure()
    assert cb.is_open()
    # Simulate the reset window having elapsed
    cb._tripped_at = datetime.now(timezone.utc) - timedelta(minutes=11)
    assert not cb.is_open()
    assert cb._failures == 0


def test_auto_reset_before_timeout_stays_open():
    cb = CircuitBreaker("test", threshold=2, reset_minutes=10)
    cb.record_failure()
    cb.record_failure()
    cb._tripped_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    assert cb.is_open()


def test_multiple_failures_beyond_threshold_does_not_reset():
    cb = CircuitBreaker("test", threshold=3)
    for _ in range(10):
        cb.record_failure()
    assert cb.is_open()
```

**Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/unit/test_circuit_breaker.py -v
```
Expected: `ModuleNotFoundError: No module named 'core.circuit_breaker'`

**Step 3: Implement `circuit_breaker.py`**

Create `packages/core/src/core/circuit_breaker.py`:

```python
# packages/core/src/core/circuit_breaker.py
"""
In-memory circuit breaker for protecting external API calls.

State is in-memory only — resets on worker restart (intentional).
A restart is a natural recovery signal; the 10-minute backoff window is short enough
that losing it on restart is acceptable.

Usage:
    from core.circuit_breaker import llm_breaker

    if llm_breaker.is_open():
        return  # skip this run

    try:
        result = call_llm(...)
        llm_breaker.record_success()
    except Exception:
        llm_breaker.record_failure()
"""
from datetime import datetime, timezone

import structlog

log = structlog.get_logger()


class CircuitBreaker:
    def __init__(self, name: str, threshold: int = 5, reset_minutes: int = 10):
        self.name = name
        self.threshold = threshold
        self.reset_minutes = reset_minutes
        self._failures: int = 0
        self._tripped_at: datetime | None = None

    def record_failure(self) -> None:
        """Increment failure count. Trip the breaker if threshold reached."""
        self._failures += 1
        if self._failures >= self.threshold and self._tripped_at is None:
            self._tripped_at = datetime.now(timezone.utc)
            log.warning("circuit_breaker_tripped", name=self.name, failures=self._failures)

    def record_success(self) -> None:
        """Reset failure count and open the circuit."""
        if self._failures > 0 or self._tripped_at is not None:
            log.info("circuit_breaker_reset", name=self.name)
        self._failures = 0
        self._tripped_at = None

    def is_open(self) -> bool:
        """
        Returns True if the circuit is open (calls should be skipped).
        Auto-resets after the reset window has elapsed.
        """
        if self._tripped_at is None:
            return False
        elapsed = (datetime.now(timezone.utc) - self._tripped_at).total_seconds()
        if elapsed >= self.reset_minutes * 60:
            self._failures = 0
            self._tripped_at = None
            log.info("circuit_breaker_auto_reset", name=self.name)
            return False
        return True


# Module-level instance — shared across all calls to job_extract_pending
llm_breaker = CircuitBreaker("llm")
```

**Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/unit/test_circuit_breaker.py -v
```
Expected: 8 passed

**Step 5: Commit**

```bash
git add packages/core/src/core/circuit_breaker.py tests/unit/test_circuit_breaker.py
git commit -m "feat: add circuit_breaker.py — in-memory LLM extraction guard"
```

---

## Task 3: Harden `jobs.py` — Wrap All Jobs + Heartbeat

**Files:**
- Modify: `apps/worker/src/worker/jobs.py`

**Step 1: Replace `jobs.py` entirely**

The new version wraps every job in `try/except`, adds `_last_poll` tracking on success,
and adds `job_heartbeat()`. No logic changes — only error handling added around existing calls.

```python
# apps/worker/src/worker/jobs.py
from datetime import datetime, timezone

from core.pipeline.normalizer import normalize_all_pending
from core.llm.extractor import extract_all_pending
from core.pipeline.reminders import (
    dispatch_due_reminders,
    schedule_reminders_for_task,
    get_policy_cadence,
)
from core.pvi.engine import compute_pvi_daily
from core.digest.generator import generate_digest
from core.db.engine import get_db
from core.db.models import ActionItem, User
from core.config import get_settings
from core.health import alert
from core.circuit_breaker import llm_breaker
import structlog

log = structlog.get_logger()

# Tracks last successful poll time per source. Used by job_heartbeat().
_last_poll: dict[str, datetime] = {}
_STALE_MINUTES = 30


def job_poll_and_normalize():
    """Poll Gmail for all configured sources and normalize new raw events."""
    try:
        from connectors.gmail.poller import poll_gmail
        with get_db() as db:
            from core.db.models import Source
            sources = db.query(Source).filter_by(source_type="gmail").all()
            source_pairs = [(str(s.user_id), str(s.id)) for s in sources]

        for user_id, source_id in source_pairs:
            poll_gmail(user_id, source_id)

        normalize_all_pending()
        _last_poll["gmail"] = datetime.now(timezone.utc)

    except RuntimeError as exc:
        msg = str(exc).lower()
        if "not connected" in msg or "auth" in msg or "credentials" in msg:
            alert("gmail_auth", "Gmail auth expired. Run: `claw connect gmail`")
        else:
            alert("gmail_poll_error", f"Gmail poll failed: {exc}", level="error")
        log.error("job_poll_gmail_failed", error=str(exc))
    except Exception as exc:
        alert("gmail_poll_error", f"Gmail poll failed: {exc}", level="error")
        log.error("job_poll_gmail_failed", error=str(exc))


def job_extract_pending():
    """Run LLM extraction on all pending messages. Protected by circuit breaker."""
    if llm_breaker.is_open():
        log.info("llm_circuit_open_skipping_extraction")
        return

    try:
        settings = get_settings()
        success, failed = extract_all_pending(settings.llm_prompt_version)
        log.info("extraction_job_done", success=success, failed=failed)

        if failed > 0 and success == 0:
            # All attempts failed this run
            llm_breaker.record_failure()
            if llm_breaker.is_open():
                alert(
                    "llm_circuit_open",
                    "LLM extraction paused (5 consecutive all-fail runs). Will retry in 10 min.",
                    level="error",
                )
        else:
            was_failing = llm_breaker._failures > 0
            llm_breaker.record_success()
            if was_failing:
                alert("llm_circuit_reset", "LLM extraction resumed.", level="info")

    except Exception as exc:
        alert("extract_job_error", f"Extraction job failed: {exc}", level="error")
        log.error("job_extract_failed", error=str(exc))
        llm_breaker.record_failure()
        if llm_breaker.is_open():
            alert(
                "llm_circuit_open",
                "LLM extraction paused (5 consecutive failures). Will retry in 10 min.",
                level="error",
            )


def job_schedule_reminders():
    """Schedule and dispatch due reminders."""
    try:
        with get_db() as db:
            tasks = db.query(ActionItem).filter(
                ActionItem.status.in_(["active", "proposed"]),
                ActionItem.due_at.isnot(None),
            ).all()
            task_pairs = [(str(t.id), str(t.user_id)) for t in tasks]

        for task_id, user_id in task_pairs:
            cadence = get_policy_cadence(user_id)
            schedule_reminders_for_task(task_id, cadence)

        dispatch_due_reminders()

    except Exception as exc:
        alert("reminder_job_error", f"Reminder dispatch failed: {exc}", level="error")
        log.error("job_reminders_failed", error=str(exc))


def job_poll_outlook():
    """Poll Outlook/Exchange via Microsoft Graph delta sync."""
    try:
        from connectors.outlook.poller import poll_outlook
        from core.db.models import Source
        with get_db() as db:
            sources = db.query(Source).filter_by(source_type="outlook").all()
            pairs = [(str(s.user_id), str(s.id)) for s in sources]
        for user_id, source_id in pairs:
            poll_outlook(user_id, source_id)
        _last_poll["outlook"] = datetime.now(timezone.utc)

    except RuntimeError as exc:
        msg = str(exc).lower()
        if "not connected" in msg or "auth" in msg:
            alert("outlook_auth", "Outlook auth expired. Run: `claw connect outlook`")
        else:
            alert("outlook_poll_error", f"Outlook poll failed: {exc}", level="error")
        log.error("job_poll_outlook_failed", error=str(exc))
    except Exception as exc:
        alert("outlook_poll_error", f"Outlook poll failed: {exc}", level="error")
        log.error("job_poll_outlook_failed", error=str(exc))


def job_poll_gcal():
    """Poll Google Calendar for upcoming events."""
    try:
        from connectors.gcal.poller import poll_gcal
        from core.db.models import Source
        with get_db() as db:
            sources = db.query(Source).filter_by(source_type="gcal").all()
            pairs = [(str(s.user_id), str(s.id)) for s in sources]
        for user_id, source_id in pairs:
            poll_gcal(user_id, source_id)
        _last_poll["gcal"] = datetime.now(timezone.utc)

    except Exception as exc:
        alert("gcal_poll_error", f"GCal poll failed: {exc}", level="error")
        log.error("job_poll_gcal_failed", error=str(exc))


def job_meeting_prep():
    """Generate and push meeting prep summaries for upcoming calendar events."""
    try:
        from core.calendar.prep import generate_prep_for_upcoming
        from core.telegram_client import send_message

        settings = get_settings()
        summaries = generate_prep_for_upcoming(settings.default_user_id)
        for msg in summaries:
            send_message(msg)

    except Exception as exc:
        log.error("job_meeting_prep_failed", error=str(exc))


def job_daily_pvi_and_digest():
    """Compute daily PVI score and push digest to Telegram (7am cron)."""
    try:
        from core.telegram_client import send_digest

        with get_db() as db:
            user_ids = [str(u.id) for u in db.query(User).all()]

        for user_id in user_ids:
            compute_pvi_daily(user_id)
            content = generate_digest(user_id)
            sent = send_digest(content)
            log.info("daily_digest_pushed", user_id=user_id, telegram_sent=sent)

    except Exception as exc:
        log.error("job_daily_digest_failed", error=str(exc))


def job_heartbeat():
    """
    Check for stale poll sources. Runs every 5 minutes.
    Fires a Telegram alert if any source hasn't polled in >30 min.
    Only alerts for sources that have polled at least once (_last_poll entry exists).
    """
    now = datetime.now(timezone.utc)
    threshold_seconds = _STALE_MINUTES * 60

    for source, last in list(_last_poll.items()):
        if (now - last).total_seconds() > threshold_seconds:
            alert(
                f"stale_{source}",
                f"No {source.title()} sync in {_STALE_MINUTES}+ min — worker may have crashed.",
                level="warning",
                cooldown_minutes=60,
            )
```

**Step 2: Run full unit test suite**

```bash
python3 -m pytest tests/unit/ -v
```
Expected: all existing 86 tests still pass (no regressions).

**Step 3: Commit**

```bash
git add apps/worker/src/worker/jobs.py
git commit -m "feat: harden jobs.py — try/except on all jobs, circuit breaker, heartbeat"
```

---

## Task 4: Register Heartbeat in Scheduler

**Files:**
- Modify: `apps/worker/src/worker/main.py`

**Step 1: Add heartbeat job**

In `apps/worker/src/worker/main.py`, add one import and one `add_job` call:

```python
# Change the import at the top:
from worker.jobs import (
    job_poll_and_normalize,
    job_poll_outlook,
    job_poll_gcal,
    job_extract_pending,
    job_schedule_reminders,
    job_daily_pvi_and_digest,
    job_meeting_prep,
    job_heartbeat,          # <-- add this
)
```

Then in `start()`, add after `job_meeting_prep`:
```python
scheduler.add_job(job_heartbeat, IntervalTrigger(minutes=5), id="heartbeat")
```

**Step 2: Run full test suite**

```bash
python3 -m pytest tests/unit/ -v
```
Expected: all tests pass.

**Step 3: Commit**

```bash
git add apps/worker/src/worker/main.py
git commit -m "feat: register job_heartbeat in APScheduler (every 5 min)"
```

---

## Task 5: Run Full Suite + Smoke Check

**Step 1: Run all unit tests**

```bash
python3 -m pytest tests/unit/ -v
```
Expected: 86 + 7 (health) + 8 (circuit_breaker) = **101 tests, all passing**

**Step 2: Quick import smoke check**

```bash
python3 -c "
from core.health import alert
from core.circuit_breaker import llm_breaker, CircuitBreaker
from worker.jobs import job_heartbeat, job_extract_pending
from worker.main import start
print('all imports OK')
"
```
Expected: `all imports OK`

**Step 3: Commit (if any stray fixes)**

```bash
git add -p
git commit -m "fix: address any import or smoke check issues"
```

---

## Summary

| File | Action |
|------|--------|
| `packages/core/src/core/health.py` | Create — rate-limited alert dispatcher |
| `packages/core/src/core/circuit_breaker.py` | Create — in-memory LLM guard |
| `tests/unit/test_health.py` | Create — 7 tests |
| `tests/unit/test_circuit_breaker.py` | Create — 8 tests |
| `apps/worker/src/worker/jobs.py` | Modify — wrap all jobs + heartbeat |
| `apps/worker/src/worker/main.py` | Modify — register heartbeat job |
