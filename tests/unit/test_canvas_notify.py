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
