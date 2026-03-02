"""Unit tests for telegram_notify — mock send_message_with_keyboard."""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone


def _make_settings(enabled=True, min_priority=60):
    s = MagicMock()
    s.telegram_enabled = enabled
    s.bot_notify_min_priority = min_priority
    return s


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
    call_args = mock_send.call_args
    text = call_args[0][0]
    keyboard = call_args[0][1]
    assert "Submit CS3230 problem set" in text
    assert "85" in text
    # Verify all three buttons
    flat_buttons = [btn for row in keyboard for btn in row]
    callback_datas = [b["callback_data"] for b in flat_buttons]
    assert "accept:abc-123" in callback_datas
    assert "dismiss:abc-123" in callback_datas
    assert "snooze:abc-123" in callback_datas


def test_send_task_notification_low_priority_skips():
    """Priority < threshold → returns False, no send."""
    with patch("core.telegram_notify.get_settings",
               return_value=_make_settings(min_priority=60)), \
         patch("core.telegram_notify.send_message_with_keyboard") as mock_send:
        from core.telegram_notify import send_task_notification
        result = send_task_notification("abc", "Low prio task", priority=40)

    assert result is False
    mock_send.assert_not_called()


def test_send_task_notification_disabled_skips():
    """telegram_enabled=False → returns False."""
    with patch("core.telegram_notify.get_settings",
               return_value=_make_settings(enabled=False)), \
         patch("core.telegram_notify.send_message_with_keyboard") as mock_send:
        from core.telegram_notify import send_task_notification
        result = send_task_notification("abc", "Task", priority=90)

    assert result is False
    mock_send.assert_not_called()


def test_send_task_notification_with_due_date():
    """due_at populated → appears in message text."""
    due = datetime(2026, 3, 7, 23, 59, tzinfo=timezone.utc)
    with patch("core.telegram_notify.get_settings",
               return_value=_make_settings()), \
         patch("core.telegram_notify.send_message_with_keyboard",
               return_value=True) as mock_send:
        from core.telegram_notify import send_task_notification
        send_task_notification("abc", "Assignment", priority=70, due_at=due)

    text = mock_send.call_args[0][0]
    assert "07 Mar" in text or "Mar" in text  # due date appears
