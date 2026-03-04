"""Unit tests for dashboard REST API endpoints."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../packages/core/src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../apps/api/src'))

from unittest.mock import MagicMock, patch
import datetime as dt


def _patch_settings():
    ms = MagicMock()
    ms.dashboard_api_key = ""
    ms.default_user_id = "uid-1"
    return ms


def test_get_tasks_returns_list():
    mock_item = MagicMock()
    mock_item.id = "task-uuid-1"
    mock_item.title = "Reply to Prof Chen"
    mock_item.details = ""
    mock_item.due_at = None
    mock_item.priority = 75
    mock_item.status = "proposed"

    mock_db = MagicMock()
    mock_db.__enter__ = lambda s: mock_db
    mock_db.__exit__ = MagicMock(return_value=False)
    mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [mock_item]

    with patch("core.db.engine.get_db", return_value=mock_db), \
         patch("core.config.get_settings", return_value=_patch_settings()):
        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        resp = client.get("/api/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["title"] == "Reply to Prof Chen"


def test_get_pvi_today_no_score():
    mock_db = MagicMock()
    mock_db.__enter__ = lambda s: mock_db
    mock_db.__exit__ = MagicMock(return_value=False)
    mock_db.query.return_value.filter.return_value.first.return_value = None

    with patch("core.db.engine.get_db", return_value=mock_db), \
         patch("core.config.get_settings", return_value=_patch_settings()):
        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        resp = client.get("/api/pvi/today")
        assert resp.status_code == 200
        assert resp.json()["score"] is None


def test_accept_task_sets_status():
    mock_item = MagicMock()
    mock_item.status = "proposed"

    mock_db = MagicMock()
    mock_db.__enter__ = lambda s: mock_db
    mock_db.__exit__ = MagicMock(return_value=False)
    mock_db.query.return_value.filter.return_value.first.return_value = mock_item

    with patch("core.db.engine.get_db", return_value=mock_db), \
         patch("core.config.get_settings", return_value=_patch_settings()):
        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        resp = client.post("/api/tasks/task-uuid-1/accept")
        assert resp.status_code == 200
        assert mock_item.status == "active"
