"""Unit tests for dashboard API key auth."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../packages/core/src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../apps/api/src'))

from unittest.mock import patch


def test_valid_api_key_returns_200():
    with patch("core.config.get_settings") as mock_settings:
        mock_settings.return_value.dashboard_api_key = "secret"
        from api.auth import get_api_key
        from fastapi import FastAPI, Depends
        from fastapi.testclient import TestClient
        app = FastAPI()

        @app.get("/protected")
        def _p(key=Depends(get_api_key)):
            return {"ok": True}

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/protected", headers={"X-API-Key": "secret"})
        assert resp.status_code == 200


def test_invalid_api_key_returns_403():
    with patch("core.config.get_settings") as mock_settings:
        mock_settings.return_value.dashboard_api_key = "secret"
        from api.auth import get_api_key
        from fastapi import FastAPI, Depends
        from fastapi.testclient import TestClient
        app = FastAPI()

        @app.get("/protected")
        def _p(key=Depends(get_api_key)):
            return {"ok": True}

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/protected", headers={"X-API-Key": "wrong"})
        assert resp.status_code == 403
