# T4: Telegram Email Reply Workflow — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** When the LLM creates a ReplyDraft, push a Telegram notification with a preview and Send/Skip buttons. Tapping Send fires the Gmail API; tapping Skip marks the draft dismissed.

**Architecture:** Add `send_reply_notification(draft_id, message_id, sender, subject, preview)` in a new `reply_notify.py`. Call it from `extractor.py` after `db.commit()` for each new ReplyDraft. Add `reply_send:draft_id` and `reply_skip:draft_id` handlers to the existing `callbacks.py` in `apps/bot/`. Gmail send logic mirrors `reply.py`.

**Tech Stack:** httpx (via existing `telegram_client.py`), structlog, google-api-python-client (already installed via `packages/connectors`).

**Test command:** `PYTHONPATH=packages/core/src:packages/connectors/src:packages/cli/src python3 -m pytest tests/unit/ -v`

---

## Task 1: Create `reply_notify.py` + 4 tests

**Files:**
- Create: `packages/core/src/core/reply_notify.py`
- Create: `tests/unit/test_reply_notify.py`

**Step 1: Write the failing tests**

Create `tests/unit/test_reply_notify.py`:

```python
"""Unit tests for reply_notify — mock telegram_client."""
from unittest.mock import patch, MagicMock
from core.reply_notify import send_reply_notification


def _make_settings(enabled=True):
    s = MagicMock()
    s.telegram_enabled = enabled
    return s


def test_reply_notification_sends_with_keyboard():
    """Send notification → uses send_message_with_keyboard with Send + Skip buttons."""
    with patch("core.reply_notify.get_settings", return_value=_make_settings()), \
         patch("core.reply_notify.send_message_with_keyboard", return_value=True) as mock_kb, \
         patch("core.reply_notify.send_message") as mock_plain:
        result = send_reply_notification(
            draft_id="draft-001",
            message_id="msg-001",
            sender="alice@example.com",
            subject="Project meeting",
            preview="Hi Alice, Saturday works for me!",
        )

    assert result is True
    mock_kb.assert_called_once()
    mock_plain.assert_not_called()
    text = mock_kb.call_args[0][0]
    assert "alice@example.com" in text
    assert "Project meeting" in text
    assert "Hi Alice" in text


def test_reply_notification_keyboard_buttons():
    """Keyboard has Send (callback reply_send:id) and Skip (callback reply_skip:id) buttons."""
    with patch("core.reply_notify.get_settings", return_value=_make_settings()), \
         patch("core.reply_notify.send_message_with_keyboard", return_value=True) as mock_kb:
        send_reply_notification("draft-abc", "msg-abc", "bob@x.com", "Sub", "preview text")

    keyboard = mock_kb.call_args[0][1]
    flat = [btn for row in keyboard for btn in row]
    cb_data = [btn.get("callback_data", "") for btn in flat]
    assert "reply_send:draft-abc" in cb_data
    assert "reply_skip:draft-abc" in cb_data


def test_reply_notification_disabled():
    """telegram_enabled=False → returns False, nothing sent."""
    with patch("core.reply_notify.get_settings", return_value=_make_settings(enabled=False)), \
         patch("core.reply_notify.send_message_with_keyboard") as mock_kb:
        result = send_reply_notification("d1", "m1", "x@x.com", "sub", "preview")

    assert result is False
    mock_kb.assert_not_called()


def test_reply_notification_truncates_long_preview():
    """Long draft preview is truncated to ≤200 chars in the notification text."""
    long_preview = "x" * 500
    with patch("core.reply_notify.get_settings", return_value=_make_settings()), \
         patch("core.reply_notify.send_message_with_keyboard", return_value=True) as mock_kb:
        send_reply_notification("d1", "m1", "x@x.com", "sub", long_preview)

    text = mock_kb.call_args[0][0]
    # Text should contain at most 200 chars of the preview, not 500
    assert "x" * 201 not in text
```

**Step 2: Run tests to verify they fail**

```bash
cd /Users/aryanganju/Desktop/Code/LifeOps
PYTHONPATH=packages/core/src:packages/connectors/src:packages/cli/src \
  python3 -m pytest tests/unit/test_reply_notify.py -v 2>&1 | tail -10
```

Expected: FAILED — `ModuleNotFoundError: No module named 'core.reply_notify'`

**Step 3: Implement `reply_notify.py`**

Create `packages/core/src/core/reply_notify.py`:

```python
# packages/core/src/core/reply_notify.py
"""
Push an immediate reply-draft notification to Telegram when an LLM ReplyDraft is created.

Called by extractor.py after successful commit.
Fail-soft: never raises, never blocks extraction.
"""
from __future__ import annotations

import structlog

from core.config import get_settings
from core.telegram_client import send_message_with_keyboard

log = structlog.get_logger()

_PREVIEW_MAX = 200


def send_reply_notification(
    draft_id: str,
    message_id: str,
    sender: str,
    subject: str,
    preview: str,
) -> bool:
    """
    Push a reply-draft notification to Telegram.

    Returns True on success, False if skipped or failed. Never raises.

    Args:
        draft_id: ReplyDraft UUID (for callback routing).
        message_id: Message UUID (for logging only).
        sender: Original email sender address.
        subject: Email subject.
        preview: First N chars of draft text.
    """
    settings = get_settings()
    if not settings.telegram_enabled:
        return False

    truncated = preview[:_PREVIEW_MAX] + ("…" if len(preview) > _PREVIEW_MAX else "")
    text = (
        f"✉️ *Reply draft ready*\n"
        f"From: {sender}\n"
        f"Re: {subject}\n\n"
        f"_{truncated}_"
    )

    keyboard = [[
        {"text": "✉️ Send", "callback_data": f"reply_send:{draft_id}"},
        {"text": "✗ Skip", "callback_data": f"reply_skip:{draft_id}"},
    ]]

    try:
        return send_message_with_keyboard(text, keyboard)
    except Exception as exc:
        log.error("reply_notify_failed", draft_id=draft_id, message_id=message_id,
                  error=str(exc), exc_info=True)
        return False
```

**Step 4: Run tests**

```bash
PYTHONPATH=packages/core/src:packages/connectors/src:packages/cli/src \
  python3 -m pytest tests/unit/test_reply_notify.py -v 2>&1 | tail -10
```

Expected: 4/4 PASS.

**Step 5: Commit**

```bash
git add packages/core/src/core/reply_notify.py tests/unit/test_reply_notify.py
git commit -m "feat(reply): add send_reply_notification helper"
```

---

## Task 2: Wire reply_notify into `extractor.py`

**Files:**
- Modify: `packages/core/src/core/llm/extractor.py`

**Step 1: Identify the insertion point**

In `extract_message()` (the main extraction function in `extractor.py`), after the final `db.commit()` and `log.info("extraction_saved", ...)` block, find the section that handles Telegram task notifications. The ReplyDraft notification should be added right after that block.

Current structure after `db.commit()` (around line 347):
```python
    # Push Telegram notification for high-priority tasks (fail-soft)
    if extraction:
        from core.telegram_notify import send_task_notification
        for item in extraction.action_items:
            ...
```

**Step 2: Add the reply notification block**

After the action_item notification loop (end of the `if extraction:` block), add:

```python
        # Push reply draft notification (fail-soft)
        if extraction.reply_drafts:
            from core.reply_notify import send_reply_notification
            for draft in extraction.reply_drafts:
                try:
                    with get_db() as db:
                        from core.db.models import ReplyDraft as ReplyDraftModel
                        saved = db.query(ReplyDraftModel).filter_by(
                            message_id=message_id,
                            tone=draft.tone,
                        ).order_by(ReplyDraftModel.created_at.desc()).first()
                        saved_id = str(saved.id) if saved else None
                    if saved_id:
                        send_reply_notification(
                            draft_id=saved_id,
                            message_id=message_id,
                            sender=msg_data["sender"],
                            subject=msg_data["title"],
                            preview=draft.draft_text,
                        )
                except Exception as exc:
                    log.warning("reply_notify_lookup_failed", error=str(exc))
```

**Step 3: Run full test suite**

```bash
cd /Users/aryanganju/Desktop/Code/LifeOps
PYTHONPATH=packages/core/src:packages/connectors/src:packages/cli/src \
  python3 -m pytest tests/unit/ -v 2>&1 | tail -10
```

Expected: 123+ PASS (119 + 4 new).

**Step 4: Commit**

```bash
git add packages/core/src/core/llm/extractor.py
git commit -m "feat(reply): push Telegram notification when reply draft created"
```

---

## Task 3: Add `reply_send` and `reply_skip` callback handlers

**Files:**
- Modify: `apps/bot/src/bot/handlers/callbacks.py`
- Modify: `apps/bot/src/bot/main.py` (verify handler is registered — it should be, since `CallbackQueryHandler` handles all callbacks)

**Step 1: Write the failing tests**

Add to `tests/unit/test_bot_callbacks.py`:

```python
@pytest.mark.asyncio
async def test_reply_send_callback_marks_sent():
    """reply_send:draft_id → draft.status updated to 'sent' and Gmail send attempted."""
    update = _make_update("reply_send:draft-send-001")
    ctx = MagicMock()

    mock_draft = MagicMock()
    mock_draft.id = "draft-send-001"
    mock_draft.draft_text = "Hi Alice, Saturday works for me!"
    mock_draft.status = "proposed"

    mock_msg = MagicMock()
    mock_msg.sender = "alice@example.com"
    mock_msg.title = "Project meeting"
    mock_msg.external_id = "gmail-thread-001"

    db = MagicMock()
    db.__enter__ = lambda s: db
    db.__exit__ = MagicMock(return_value=False)
    db.query.return_value.filter_by.return_value.first.side_effect = [mock_draft, mock_msg]

    with patch("bot.handlers.callbacks.get_db", return_value=db), \
         patch("bot.handlers.callbacks._send_gmail_reply", return_value=True) as mock_gmail:
        await handle_callback(update, ctx)

    update.callback_query.edit_message_text.assert_called_once()
    text = update.callback_query.edit_message_text.call_args[0][0]
    assert "Sent" in text or "sent" in text


@pytest.mark.asyncio
async def test_reply_skip_callback_marks_dismissed():
    """reply_skip:draft_id → draft.status = 'dismissed', confirmation sent."""
    update = _make_update("reply_skip:draft-skip-001")
    ctx = MagicMock()

    mock_draft = MagicMock()
    mock_draft.id = "draft-skip-001"
    mock_draft.status = "proposed"

    db = MagicMock()
    db.__enter__ = lambda s: db
    db.__exit__ = MagicMock(return_value=False)
    db.query.return_value.filter_by.return_value.first.return_value = mock_draft

    with patch("bot.handlers.callbacks.get_db", return_value=db):
        await handle_callback(update, ctx)

    update.callback_query.edit_message_text.assert_called_once()
    text = update.callback_query.edit_message_text.call_args[0][0]
    assert "Skip" in text or "skip" in text or "✗" in text
```

**Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=packages/core/src:packages/connectors/src:packages/cli/src:apps/bot/src \
  python3 -m pytest tests/unit/test_bot_callbacks.py -v 2>&1 | tail -10
```

Expected: FAIL — `_send_gmail_reply` not found.

**Step 3: Implement handlers in `callbacks.py`**

In `apps/bot/src/bot/handlers/callbacks.py`:

1. Add imports at the top of the file:
```python
from core.db.models import ActionItem, Reminder, ReplyDraft, Message
```

2. Add `_send_gmail_reply` helper (extracted from `reply.py` logic):
```python
def _send_gmail_reply(draft_text: str, to: str, subject: str, thread_id: str | None) -> bool:
    """Send a Gmail reply. Returns True on success, raises on failure."""
    import base64
    import email.mime.text
    from connectors.gmail.auth import get_credentials
    from googleapiclient.discovery import build

    creds = get_credentials()
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    mime_msg = email.mime.text.MIMEText(draft_text)
    mime_msg["To"] = to
    mime_msg["Subject"] = f"Re: {subject}" if not subject.startswith("Re:") else subject
    if thread_id:
        mime_msg["In-Reply-To"] = thread_id
        mime_msg["References"] = thread_id

    raw = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode()
    service.users().messages().send(
        userId="me",
        body={"raw": raw, "threadId": thread_id},
    ).execute()
    return True
```

3. Update `handle_callback` to route `reply_send` and `reply_skip`:
```python
    if action == "accept":
        await _accept(query, task_id)
    elif action == "dismiss":
        await _dismiss(query, task_id)
    elif action == "snooze":
        await _snooze(query, task_id)
    elif action == "reply_send":
        await _reply_send(query, task_id)
    elif action == "reply_skip":
        await _reply_skip(query, task_id)
    else:
        await query.edit_message_text("⚠️ Unknown action.")
```

4. Add the two new handler coroutines:
```python
async def _reply_send(query, draft_id: str) -> None:
    try:
        with get_db() as db:
            draft = db.query(ReplyDraft).filter_by(id=draft_id).first()
            if not draft:
                await query.edit_message_text("⚠️ Draft not found.")
                return
            draft_text = draft.draft_text
            message_id = str(draft.message_id)

        with get_db() as db:
            msg = db.query(Message).filter_by(id=message_id).first()
            if not msg:
                await query.edit_message_text("⚠️ Message not found.")
                return
            to = msg.sender
            subject = msg.title
            thread_id = msg.external_id

        _send_gmail_reply(draft_text, to, subject, thread_id)

        with get_db() as db:
            draft = db.query(ReplyDraft).filter_by(id=draft_id).first()
            if draft:
                draft.status = "sent"
        log.info("reply_sent_via_bot", draft_id=draft_id)
        await query.edit_message_text("✓ *Reply sent\\!*", parse_mode="MarkdownV2")
    except Exception:
        log.exception("reply_send_callback_error", draft_id=draft_id)
        await query.edit_message_text("⚠️ Failed to send reply. Try `claw reply send` instead.")


async def _reply_skip(query, draft_id: str) -> None:
    try:
        with get_db() as db:
            draft = db.query(ReplyDraft).filter_by(id=draft_id).first()
            if not draft:
                await query.edit_message_text("⚠️ Draft not found.")
                return
            draft.status = "dismissed"
        log.info("reply_skipped_via_bot", draft_id=draft_id)
        await query.edit_message_text("✗ *Reply skipped*", parse_mode="MarkdownV2")
    except Exception:
        log.exception("reply_skip_callback_error", draft_id=draft_id)
        await query.edit_message_text("⚠️ Something went wrong.")
```

**Step 4: Verify `main.py` already handles all callbacks**

Check `apps/bot/src/bot/main.py` — the `CallbackQueryHandler(handle_callback)` should already be registered without a pattern, meaning it handles ALL callback queries including `reply_send:*` and `reply_skip:*`. No change needed to `main.py`.

**Step 5: Run full test suite**

```bash
cd /Users/aryanganju/Desktop/Code/LifeOps
PYTHONPATH=packages/core/src:packages/connectors/src:packages/cli/src:apps/bot/src \
  python3 -m pytest tests/unit/ -v 2>&1 | tail -10
```

Expected: 125+ PASS.

**Step 6: Update phase3 tracker**

In `docs/plans/2026-03-02-clawdbot-phase3.md`, mark T4 done:
```
- [x] Task 4: Telegram email reply workflow — full thread → LLM draft → approve → send ✅ DONE
```

**Step 7: Commit**

```bash
git add apps/bot/src/bot/handlers/callbacks.py \
        docs/plans/2026-03-02-clawdbot-phase3.md
git commit -m "feat(reply): add reply_send/reply_skip Telegram bot callbacks"
```
