"""Smoke test: bot Application builds without error."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../apps/bot/src'))

import pytest
from unittest.mock import patch, MagicMock


def test_build_app_requires_token():
    """build_app raises RuntimeError if TELEGRAM_BOT_TOKEN is empty."""
    from bot.main import build_app

    s = MagicMock()
    s.telegram_bot_token = ""

    with patch("bot.main.get_settings", return_value=s):
        with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
            build_app()
