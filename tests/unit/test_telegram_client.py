# tests/unit/test_telegram_client.py
"""Unit tests for telegram_client — mocks httpx, never makes real API calls."""
import pytest
from unittest.mock import patch, MagicMock
from core.telegram_client import send_message, send_digest


def _make_settings(enabled=True, token="bot123", chat_id="456"):
    s = MagicMock()
    s.telegram_enabled = enabled
    s.telegram_bot_token = token
    s.telegram_chat_id = chat_id
    return s


def test_send_message_disabled_returns_false():
    with patch("core.telegram_client.get_settings", return_value=_make_settings(enabled=False)):
        assert send_message("hello") is False


def test_send_message_no_token_returns_false():
    with patch("core.telegram_client.get_settings",
               return_value=_make_settings(token="", chat_id="")):
        assert send_message("hello") is False


def test_send_message_success():
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None

    with patch("core.telegram_client.get_settings", return_value=_make_settings()), \
         patch("httpx.post", return_value=mock_resp) as mock_post:
        result = send_message("hello world")

    assert result is True
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert "hello world" in str(call_kwargs)


def test_send_message_http_error_returns_false():
    import httpx

    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"

    with patch("core.telegram_client.get_settings", return_value=_make_settings()), \
         patch("httpx.post", side_effect=httpx.HTTPStatusError(
             "401", request=MagicMock(), response=mock_resp)):
        result = send_message("hello")

    assert result is False


def test_send_message_network_error_returns_false():
    with patch("core.telegram_client.get_settings", return_value=_make_settings()), \
         patch("httpx.post", side_effect=Exception("network timeout")):
        result = send_message("hello")

    assert result is False


def test_send_digest_short_message_single_call():
    with patch("core.telegram_client.get_settings", return_value=_make_settings()), \
         patch("core.telegram_client.send_message", return_value=True) as mock_send:
        result = send_digest("# Short digest\nSome content")

    assert result is True
    mock_send.assert_called_once()


def test_send_digest_long_message_chunks():
    # 4100 char message — should be split
    long_text = "A" * 2100 + "\n\n" + "B" * 2100

    with patch("core.telegram_client.get_settings", return_value=_make_settings()), \
         patch("core.telegram_client.send_message", return_value=True) as mock_send:
        result = send_digest(long_text)

    assert result is True
    assert mock_send.call_count >= 2  # Should chunk into multiple messages
