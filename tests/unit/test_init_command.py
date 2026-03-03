"""Unit tests for claw init command."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../packages/core/src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../packages/cli/src'))

from unittest.mock import MagicMock, patch


def _make_settings(**overrides):
    s = MagicMock()
    s.user_email = overrides.get("user_email", "test@example.com")
    s.user_display_name = overrides.get("user_display_name", "Test User")
    s.user_timezone = "Asia/Singapore"
    s.default_user_id = "00000000-0000-0000-0000-000000000001"
    return s


def test_init_creates_user_row():
    """When no existing user found, db.add and db.commit are called with correct attrs."""
    mock_db = MagicMock()
    mock_db.__enter__ = lambda s: mock_db
    mock_db.__exit__ = MagicMock(return_value=False)
    mock_db.query.return_value.filter.return_value.first.return_value = None

    with patch("core.config.get_settings", return_value=_make_settings()), \
         patch("core.db.engine.get_db", return_value=mock_db), \
         patch("pathlib.Path.exists", return_value=False):
        from cli.commands.init import cmd_init
        cmd_init()

    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()
    added_user = mock_db.add.call_args[0][0]
    assert added_user.email == "test@example.com"
    assert added_user.display_name == "Test User"


def test_init_idempotent_existing_user():
    """When user already exists, db.add is NOT called."""
    mock_existing = MagicMock()
    mock_existing.id = "existing-uuid"
    mock_existing.display_name = "Existing User"

    mock_db = MagicMock()
    mock_db.__enter__ = lambda s: mock_db
    mock_db.__exit__ = MagicMock(return_value=False)
    mock_db.query.return_value.filter.return_value.first.return_value = mock_existing

    with patch("core.config.get_settings", return_value=_make_settings()), \
         patch("core.db.engine.get_db", return_value=mock_db):
        from cli.commands.init import cmd_init
        cmd_init()

    mock_db.add.assert_not_called()
    mock_db.commit.assert_not_called()
