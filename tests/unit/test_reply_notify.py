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
