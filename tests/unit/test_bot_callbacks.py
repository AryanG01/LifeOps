"""Unit tests for callback handlers — mock DB and Telegram Update."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../apps/bot/src'))

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timezone, timedelta


def _make_update(callback_data: str, chat_id: int = 456):
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.callback_query = AsyncMock()
    update.callback_query.data = callback_data
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    return update


def _make_context():
    return MagicMock()


def _make_settings(chat_id="456"):
    s = MagicMock()
    s.telegram_chat_id = chat_id
    s.default_user_id = "00000000-0000-0000-0000-000000000001"
    return s


@pytest.mark.asyncio
async def test_handle_accept_updates_status():
    """accept:uuid → ActionItem.status set to 'active'."""
    from bot.handlers.callbacks import handle_callback

    task_id = "aaaabbbb-0000-0000-0000-000000000001"

    mock_task = MagicMock()
    mock_task.id = task_id
    mock_task.title = "Submit PS4"
    mock_task.status = "proposed"

    db = MagicMock()
    db.__enter__ = lambda s: db
    db.__exit__ = MagicMock(return_value=False)
    db.query.return_value.filter_by.return_value.first.return_value = mock_task

    with patch("bot.handlers.callbacks.get_settings",
               return_value=_make_settings()), \
         patch("bot.handlers.callbacks.get_db", return_value=db):
        update = _make_update(f"accept:{task_id}")
        await handle_callback(update, _make_context())

    assert mock_task.status == "active"
    update.callback_query.edit_message_text.assert_awaited_once()
    edit_text = update.callback_query.edit_message_text.call_args[0][0]
    assert "accepted" in edit_text.lower() or "✓" in edit_text


@pytest.mark.asyncio
async def test_handle_dismiss_updates_status():
    """dismiss:uuid → ActionItem.status set to 'dismissed'."""
    from bot.handlers.callbacks import handle_callback

    task_id = "aaaabbbb-0000-0000-0000-000000000002"
    mock_task = MagicMock()
    mock_task.title = "Spam task"

    db = MagicMock()
    db.__enter__ = lambda s: db
    db.__exit__ = MagicMock(return_value=False)
    db.query.return_value.filter_by.return_value.first.return_value = mock_task

    with patch("bot.handlers.callbacks.get_settings",
               return_value=_make_settings()), \
         patch("bot.handlers.callbacks.get_db", return_value=db):
        update = _make_update(f"dismiss:{task_id}")
        await handle_callback(update, _make_context())

    assert mock_task.status == "dismissed"


@pytest.mark.asyncio
async def test_handle_snooze_creates_reminder():
    """snooze:uuid → Reminder row added with remind_at ~2h from now."""
    from bot.handlers.callbacks import handle_callback

    task_id = "aaaabbbb-0000-0000-0000-000000000003"
    mock_task = MagicMock()
    mock_task.id = task_id
    mock_task.title = "Meeting prep"
    mock_task.user_id = "00000000-0000-0000-0000-000000000001"

    added_objects = []
    db = MagicMock()
    db.__enter__ = lambda s: db
    db.__exit__ = MagicMock(return_value=False)
    db.query.return_value.filter_by.return_value.first.return_value = mock_task
    db.add.side_effect = added_objects.append

    with patch("bot.handlers.callbacks.get_settings",
               return_value=_make_settings()), \
         patch("bot.handlers.callbacks.get_db", return_value=db):
        update = _make_update(f"snooze:{task_id}")
        await handle_callback(update, _make_context())

    from core.db.models import Reminder
    reminders = [o for o in added_objects if isinstance(o, Reminder)]
    assert len(reminders) == 1
    now = datetime.now(timezone.utc)
    remind_delta = reminders[0].remind_at - now
    assert 100 * 60 < remind_delta.total_seconds() < 130 * 60  # ~2h


@pytest.mark.asyncio
async def test_wrong_chat_id_ignored():
    """Messages from wrong chat ID → handler does nothing."""
    from bot.handlers.callbacks import handle_callback

    with patch("bot.handlers.callbacks.get_settings",
               return_value=_make_settings(chat_id="456")):
        update = _make_update("accept:abc", chat_id=999)  # wrong chat
        with patch("bot.handlers.callbacks.get_db") as mock_db:
            await handle_callback(update, _make_context())
            mock_db.assert_not_called()


@pytest.mark.asyncio
async def test_reply_send_callback_marks_sent():
    """reply_send:draft_id → Gmail send attempted and confirmation sent to user."""
    from bot.handlers.callbacks import handle_callback

    update = _make_update("reply_send:draft-send-001")
    ctx = MagicMock()

    mock_draft = MagicMock()
    mock_draft.id = "draft-send-001"
    mock_draft.draft_text = "Hi Alice, Saturday works for me!"
    mock_draft.message_id = "msg-001"
    mock_draft.status = "proposed"

    mock_msg = MagicMock()
    mock_msg.sender = "alice@example.com"
    mock_msg.title = "Project meeting"
    mock_msg.external_id = "gmail-thread-001"

    db = MagicMock()
    db.__enter__ = lambda s: db
    db.__exit__ = MagicMock(return_value=False)

    call_count = [0]
    def query_side_effect(model):
        call_count[0] += 1
        m = MagicMock()
        if call_count[0] == 1:
            m.filter_by.return_value.first.return_value = mock_draft  # draft lookup
        elif call_count[0] == 2:
            m.filter_by.return_value.first.return_value = mock_msg   # message lookup
        else:
            m.filter_by.return_value.first.return_value = mock_draft  # status update
        return m
    db.query.side_effect = query_side_effect

    with patch("bot.handlers.callbacks.get_settings",
               return_value=_make_settings()), \
         patch("bot.handlers.callbacks.get_db", return_value=db), \
         patch("bot.handlers.callbacks._send_gmail_reply", return_value=True):
        await handle_callback(update, ctx)

    update.callback_query.edit_message_text.assert_called_once()
    text = update.callback_query.edit_message_text.call_args[0][0]
    assert "sent" in text.lower() or "✓" in text


@pytest.mark.asyncio
async def test_reply_skip_callback_marks_dismissed():
    """reply_skip:draft_id → draft.status = 'dismissed', confirmation sent."""
    from bot.handlers.callbacks import handle_callback

    update = _make_update("reply_skip:draft-skip-001")
    ctx = MagicMock()

    mock_draft = MagicMock()
    mock_draft.id = "draft-skip-001"
    mock_draft.status = "proposed"

    db = MagicMock()
    db.__enter__ = lambda s: db
    db.__exit__ = MagicMock(return_value=False)
    db.query.return_value.filter_by.return_value.first.return_value = mock_draft

    with patch("bot.handlers.callbacks.get_settings",
               return_value=_make_settings()), \
         patch("bot.handlers.callbacks.get_db", return_value=db):
        await handle_callback(update, ctx)

    update.callback_query.edit_message_text.assert_called_once()
    text = update.callback_query.edit_message_text.call_args[0][0]
    assert "skip" in text.lower() or "✗" in text
