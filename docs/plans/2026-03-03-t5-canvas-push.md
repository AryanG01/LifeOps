# T5: Canvas Push Notifications — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** When `normalize_raw_event()` detects a Canvas assignment/announcement, immediately push a Telegram message so the user knows before the LLM extraction cycle runs.

**Architecture:** Add `send_canvas_notification(canvas, msg_id)` in a new `canvas_notify.py`. Call it from `normalize_raw_event()` in `normalizer.py` after a successful commit, inside the try block. Uses existing `send_message()` for plain push, or `send_message_with_keyboard()` when a Canvas URL is available (URL button opens Canvas directly). Fail-soft — never crashes normalization.

**Tech Stack:** httpx (via existing `telegram_client.py`), structlog, pydantic-settings.

**Test command:** `PYTHONPATH=packages/core/src:packages/connectors/src:packages/cli/src python3 -m pytest tests/unit/ -v`

---

## Task 1: Create `canvas_notify.py` + 4 tests

**Files:**
- Create: `packages/core/src/core/canvas_notify.py`
- Create: `tests/unit/test_canvas_notify.py`

**Step 1: Write the failing tests**

Create `tests/unit/test_canvas_notify.py`:

```python
"""Unit tests for canvas_notify — mock telegram_client."""
import pytest
from unittest.mock import patch, MagicMock
from connectors.canvas.parser import CanvasParseResult


def _canvas(
    canvas_type="assignment",
    course_code="CS3230",
    assignment_title="Problem Set 4",
    due_at_raw="Mar 7, 2026",
    canvas_url=None,
):
    return CanvasParseResult(
        is_canvas=True,
        course_code=course_code,
        course_name=None,
        assignment_title=assignment_title,
        due_at_raw=due_at_raw,
        canvas_url=canvas_url,
        canvas_type=canvas_type,
    )


def _make_settings(enabled=True):
    s = MagicMock()
    s.telegram_enabled = enabled
    return s


def test_canvas_notification_assignment_plain():
    """Canvas without URL → uses send_message, text contains course + title + due."""
    with patch("core.canvas_notify.get_settings", return_value=_make_settings()), \
         patch("core.canvas_notify.send_message", return_value=True) as mock_send, \
         patch("core.canvas_notify.send_message_with_keyboard") as mock_kb:
        from core.canvas_notify import send_canvas_notification
        result = send_canvas_notification(_canvas(), "msg-1")

    assert result is True
    mock_send.assert_called_once()
    mock_kb.assert_not_called()
    text = mock_send.call_args[0][0]
    assert "CS3230" in text
    assert "Problem Set 4" in text
    assert "Mar 7" in text


def test_canvas_notification_with_url():
    """Canvas with URL → uses send_message_with_keyboard with URL button."""
    url = "https://canvas.nus.edu.sg/courses/123/assignments/456"
    with patch("core.canvas_notify.get_settings", return_value=_make_settings()), \
         patch("core.canvas_notify.send_message", return_value=True) as mock_send, \
         patch("core.canvas_notify.send_message_with_keyboard", return_value=True) as mock_kb:
        from core.canvas_notify import send_canvas_notification
        result = send_canvas_notification(_canvas(canvas_url=url), "msg-1")

    assert result is True
    mock_kb.assert_called_once()
    mock_send.assert_not_called()
    # Verify URL button is present
    keyboard = mock_kb.call_args[0][1]
    flat = [btn for row in keyboard for btn in row]
    assert any(btn.get("url") == url for btn in flat)


def test_canvas_notification_disabled():
    """telegram_enabled=False → returns False, nothing sent."""
    with patch("core.canvas_notify.get_settings", return_value=_make_settings(enabled=False)), \
         patch("core.canvas_notify.send_message") as mock_send:
        from core.canvas_notify import send_canvas_notification
        result = send_canvas_notification(_canvas(), "msg-1")

    assert result is False
    mock_send.assert_not_called()


def test_canvas_notification_announcement():
    """Announcement type uses correct emoji/label."""
    with patch("core.canvas_notify.get_settings", return_value=_make_settings()), \
         patch("core.canvas_notify.send_message", return_value=True) as mock_send:
        from core.canvas_notify import send_canvas_notification
        result = send_canvas_notification(_canvas(canvas_type="announcement", due_at_raw=None), "msg-1")

    assert result is True
    text = mock_send.call_args[0][0]
    assert "CS3230" in text
```

**Step 2: Run tests to verify they fail**

```bash
cd /Users/aryanganju/Desktop/Code/LifeOps
PYTHONPATH=packages/core/src:packages/connectors/src:packages/cli/src \
  python3 -m pytest tests/unit/test_canvas_notify.py -v 2>&1 | tail -10
```
Expected: `FAILED` — `ModuleNotFoundError: No module named 'core.canvas_notify'`

**Step 3: Implement `canvas_notify.py`**

Create `packages/core/src/core/canvas_notify.py`:

```python
# packages/core/src/core/canvas_notify.py
"""
Push an immediate Canvas notification to Telegram when a Canvas email is detected.

Called by normalize_raw_event() after successful commit.
Fail-soft: never raises, never blocks normalization.
"""
from __future__ import annotations

import structlog

from connectors.canvas.parser import CanvasParseResult
from core.config import get_settings
from core.telegram_client import send_message, send_message_with_keyboard

log = structlog.get_logger()

_TYPE_EMOJI = {
    "assignment":   "📋",
    "announcement": "📢",
    "quiz":         "📝",
    "grade":        "🏆",
}


def send_canvas_notification(canvas: CanvasParseResult, msg_id: str) -> bool:
    """
    Push a Canvas notification to Telegram.

    Returns True on success, False if skipped or failed. Never raises.

    Args:
        canvas: Parsed Canvas result (is_canvas=True assumed).
        msg_id: Message UUID (for logging).
    """
    settings = get_settings()
    if not settings.telegram_enabled:
        return False

    emoji = _TYPE_EMOJI.get(canvas.canvas_type or "", "📚")
    course = canvas.course_code or "Canvas"
    title = canvas.assignment_title or "New notification"
    canvas_type_label = (canvas.canvas_type or "notification").capitalize()

    lines = [f"{emoji} *{canvas_type_label}* — {course}", title]
    if canvas.due_at_raw:
        lines.append(f"Due: {canvas.due_at_raw}")
    text = "\n".join(lines)

    try:
        if canvas.canvas_url:
            keyboard = [[{"text": "View on Canvas", "url": canvas.canvas_url}]]
            return send_message_with_keyboard(text, keyboard)
        return send_message(text)
    except Exception as exc:
        log.error("canvas_notify_failed", msg_id=msg_id, error=str(exc))
        return False
```

**Step 4: Run tests**

```bash
PYTHONPATH=packages/core/src:packages/connectors/src:packages/cli/src \
  python3 -m pytest tests/unit/test_canvas_notify.py -v 2>&1 | tail -10
```
Expected: 4/4 PASS.

**Step 5: Commit**

```bash
git add packages/core/src/core/canvas_notify.py tests/unit/test_canvas_notify.py
git commit -m "feat(canvas): add send_canvas_notification helper"
```

---

## Task 2: Wire canvas_notify into `normalize_raw_event()`

**Files:**
- Modify: `packages/core/src/core/pipeline/normalizer.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_normalizer_multisource.py` (or create `tests/unit/test_normalizer_canvas_push.py`):

Check if there's already a test file for normalizer:
```bash
ls /Users/aryanganju/Desktop/Code/LifeOps/tests/unit/test_normalizer_multisource.py
```

Create `tests/unit/test_normalizer_canvas_push.py`:

```python
"""Test that Canvas normalization triggers immediate Telegram push."""
import pytest
from unittest.mock import patch, MagicMock


def _make_canvas_payload():
    return {
        "gmail_id": "canvas-msg-001",
        "sender": "notifications@canvas.nus.edu.sg",
        "subject": "CS3230 Assignment: Problem Set 4 due Mar 7",
        "body_text": "Assignment due Mar 7, 2026 at 11:59pm. Canvas: https://canvas.nus.edu.sg/courses/1/assignments/2",
        "internal_date": "1741000000000",
        "label_ids": ["INBOX", "UNREAD"],
    }


def test_normalize_canvas_triggers_push():
    """Successfully normalized Canvas message fires send_canvas_notification."""
    from core.pipeline.normalizer import normalize_raw_event
    from core.db.models import RawEvent

    mock_event = MagicMock(spec=RawEvent)
    mock_event.id = "evt-001"
    mock_event.user_id = "00000000-0000-0000-0000-000000000001"
    mock_event.source_id = "src-001"
    mock_event.external_id = "canvas-msg-001"
    mock_event.processed_at = None
    mock_event.payload_json = _make_canvas_payload()

    db = MagicMock()
    db.__enter__ = lambda s: db
    db.__exit__ = MagicMock(return_value=False)
    db.query.return_value.filter_by.return_value.first.return_value = mock_event

    mock_msg = MagicMock()
    mock_msg.id = "msg-canvas-001"
    db.flush.side_effect = lambda: setattr(mock_msg, "id", "msg-canvas-001")
    db.add.return_value = None

    with patch("core.pipeline.normalizer.get_db", return_value=db), \
         patch("core.pipeline.normalizer.send_canvas_notification") as mock_notify:
        # Canvas detection will fire in parse_canvas_email
        result = normalize_raw_event("evt-001")

    # Notification should have been called
    mock_notify.assert_called_once()


def test_normalize_non_canvas_no_push():
    """Non-Canvas message does NOT fire send_canvas_notification."""
    from core.pipeline.normalizer import normalize_raw_event
    from core.db.models import RawEvent

    mock_event = MagicMock(spec=RawEvent)
    mock_event.id = "evt-002"
    mock_event.user_id = "00000000-0000-0000-0000-000000000001"
    mock_event.source_id = "src-001"
    mock_event.external_id = "gmail-msg-002"
    mock_event.processed_at = None
    mock_event.payload_json = {
        "gmail_id": "gmail-msg-002",
        "sender": "alice@example.com",
        "subject": "Meeting tomorrow",
        "body_text": "Let's meet at 3pm.",
        "internal_date": "1741000000000",
        "label_ids": ["INBOX"],
    }

    db = MagicMock()
    db.__enter__ = lambda s: db
    db.__exit__ = MagicMock(return_value=False)
    db.query.return_value.filter_by.return_value.first.return_value = mock_event

    with patch("core.pipeline.normalizer.get_db", return_value=db), \
         patch("core.pipeline.normalizer.send_canvas_notification") as mock_notify:
        normalize_raw_event("evt-002")

    mock_notify.assert_not_called()
```

> **Note:** These normalizer tests use deep DB mocking that may be brittle. If they're too hard to get working cleanly, just verify the integration manually by running `claw sync` after setup. The `canvas_notify.py` unit tests (Task 1) are the primary test boundary.

**Step 2: Add the notification call to `normalizer.py`**

In `packages/core/src/core/pipeline/normalizer.py`, modify `normalize_raw_event()`:

1. Add lazy import at the top of the try block (around line 119), after `db.add(msg)` and `db.flush()` and the commit, before `return msg_id`:

The full modified try block (replace the existing try block inside `with get_db() as db:`):

```python
        try:
            db.add(msg)
            db.flush()
            msg_id = str(msg.id)
            event.processed_at = datetime.now(tz=timezone.utc)
            db.commit()
            log.info(
                "message_normalized",
                message_id=msg_id,
                raw_event_id=raw_event_id,
                is_canvas=canvas.is_canvas,
            )
            # Immediate Canvas push (fail-soft — canvas is a plain dataclass, no ORM)
            if canvas.is_canvas:
                from core.canvas_notify import send_canvas_notification
                send_canvas_notification(canvas, msg_id)
            return msg_id
```

**Step 3: Run full test suite**

```bash
cd /Users/aryanganju/Desktop/Code/LifeOps
PYTHONPATH=packages/core/src:packages/connectors/src:packages/cli/src \
  python3 -m pytest tests/unit/ -v --tb=short 2>&1 | tail -10
```
Expected: 119+ PASS (115 + 4 new canvas_notify tests).

**Step 4: Update phase3 tracker**

In `docs/plans/2026-03-02-clawdbot-phase3.md`, mark T5 done:
```
- [x] Task 5: Telegram Canvas/assignment notifications ✅ DONE
```

**Step 5: Commit**

```bash
git add packages/core/src/core/pipeline/normalizer.py \
        tests/unit/test_normalizer_canvas_push.py \
        docs/plans/2026-03-02-clawdbot-phase3.md
git commit -m "feat(canvas): push immediate Telegram notification on Canvas detection"
```
