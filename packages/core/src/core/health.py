# packages/core/src/core/health.py
"""
Rate-limited Telegram health alert dispatcher.

Usage:
    from core.health import alert
    alert("gmail_auth", "Gmail auth expired. Run: claw connect gmail")

Each alert key is suppressed within its cooldown window to prevent Telegram spam.
State is in-memory — resets on worker restart (intentional).
"""
from datetime import datetime, timezone
from typing import Literal

import structlog

from core.telegram_client import send_message

log = structlog.get_logger()

_last_alert: dict[str, datetime] = {}


def alert(
    key: str,
    message: str,
    level: Literal["warning", "error", "info"] = "warning",
    cooldown_minutes: int = 30,
) -> None:
    """
    Send a Telegram health alert, rate-limited by key. Never raises.

    Args:
        key: Deduplication key (e.g. "gmail_auth"). Same key suppressed within cooldown.
        message: Human-readable alert text.
        level: Emoji prefix — warning=⚠️, error=🔴, info=ℹ️.
        cooldown_minutes: Minimum minutes between alerts with the same key.
    """
    now = datetime.now(timezone.utc)
    last = _last_alert.get(key)
    if last is not None and (now - last).total_seconds() < cooldown_minutes * 60:
        log.debug("health_alert_suppressed", key=key)
        return

    _last_alert[key] = now
    emoji = {"warning": "⚠️", "error": "🔴", "info": "ℹ️"}.get(level, "⚠️")
    try:
        send_message(f"{emoji} *Clawdbot Alert*\n{message}")
        log.info("health_alert_sent", key=key, level=level)
    except Exception as exc:
        log.error("health_alert_failed", key=key, error=str(exc))


def reset_alerts() -> None:
    """Clear all rate-limit state. Used in tests only."""
    _last_alert.clear()
