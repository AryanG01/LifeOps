from unittest.mock import MagicMock
from datetime import datetime, timezone, timedelta


def test_is_in_focus_returns_true_during_active_session():
    from core.pipeline.reminders import _is_in_focus
    mock_db = MagicMock()
    mock_session = MagicMock()
    mock_session.ends_at = datetime.now(tz=timezone.utc) + timedelta(hours=1)
    mock_session.is_active = True
    mock_db.query.return_value.filter.return_value.first.return_value = mock_session
    assert _is_in_focus(mock_db, "user-id") is True


def test_is_in_focus_returns_false_when_no_session():
    from core.pipeline.reminders import _is_in_focus
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    assert _is_in_focus(mock_db, "user-id") is False
