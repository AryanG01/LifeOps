"""Unit tests for claw status command."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../packages/core/src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../packages/cli/src'))

from unittest.mock import MagicMock, patch


def _mock_source(source_type, display_name, last_synced_at=None):
    s = MagicMock()
    s.source_type = source_type
    s.display_name = display_name
    s.last_synced_at = last_synced_at
    return s


def _mock_user(display_name="Alice", email="alice@example.com"):
    u = MagicMock()
    u.display_name = display_name
    u.email = email
    return u


def _make_settings(uid="00000000-0000-0000-0000-000000000001"):
    s = MagicMock()
    s.default_user_id = uid
    s.telegram_bot_token = "tok"
    return s


def _make_mock_db(user, sources):
    from core.db.models import User, Source
    mock_db = MagicMock()
    mock_db.__enter__ = lambda s: mock_db
    mock_db.__exit__ = MagicMock(return_value=False)

    def query_side_effect(model):
        q = MagicMock()
        if model is User:
            q.filter.return_value.first.return_value = user
        elif model is Source:
            q.filter.return_value.all.return_value = sources
        return q

    mock_db.query.side_effect = query_side_effect
    mock_db.execute.return_value.fetchone.return_value = None
    return mock_db


def test_status_shows_user_info(capsys):
    """Status output contains user display name and email."""
    mock_db = _make_mock_db(_mock_user("Alice", "alice@example.com"), [])
    with patch("core.config.get_settings", return_value=_make_settings()), \
         patch("core.db.engine.get_db", return_value=mock_db):
        from cli.commands.status import cmd_status
        cmd_status()
    out = capsys.readouterr().out
    assert "Alice" in out
    assert "alice@example.com" in out


def test_status_shows_sources(capsys):
    """Status table contains both source types when sources exist."""
    sources = [
        _mock_source("gmail", "Gmail"),
        _mock_source("outlook", "Outlook"),
    ]
    mock_db = _make_mock_db(_mock_user(), sources)
    with patch("core.config.get_settings", return_value=_make_settings()), \
         patch("core.db.engine.get_db", return_value=mock_db):
        from cli.commands.status import cmd_status
        cmd_status()
    out = capsys.readouterr().out
    assert "gmail" in out
    assert "outlook" in out


def test_status_no_sources(capsys):
    """Status table shows fallback row when no sources connected."""
    mock_db = _make_mock_db(_mock_user(), [])
    with patch("core.config.get_settings", return_value=_make_settings()), \
         patch("core.db.engine.get_db", return_value=mock_db):
        from cli.commands.status import cmd_status
        cmd_status()
    out = capsys.readouterr().out
    assert "No sources connected" in out
