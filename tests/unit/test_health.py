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


def test_alert_retries_after_send_failure():
    """Cooldown should NOT activate when send_message returns False."""
    with patch("core.health.send_message", return_value=False):
        alert("key1", "First attempt")

    with patch("core.health.send_message") as mock_send:
        mock_send.return_value = True
        alert("key1", "Retry")
    mock_send.assert_called_once()
