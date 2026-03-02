# packages/core/src/core/telegram_notify.py
"""
Push a new ActionItem to Telegram with Accept/Dismiss/Snooze inline buttons.

Called by the LLM extractor after writing high-priority ActionItems to DB.
Fail-soft: never raises, never blocks extraction.
"""
from __future__ import annotations

from datetime import datetime

import structlog

from core.config import get_settings
from core.telegram_client import send_message_with_keyboard

log = structlog.get_logger()


def send_task_notification(
    task_id: str,
    title: str,
    priority: int,
    due_at: datetime | None = None,
) -> bool:
    """
    Push a task notification with inline keyboard to Telegram.

    Returns True on success, False if skipped or failed. Never raises.

    Args:
        task_id: ActionItem UUID (used as callback_data payload).
        title:   Task title shown in the notification.
        priority: Integer 0-100. Only sends if >= settings.bot_notify_min_priority.
        due_at:  Optional due datetime (UTC). Shown as "due DD Mon".
    """
    settings = get_settings()

    if not settings.telegram_enabled:
        return False
    if priority < settings.bot_notify_min_priority:
        log.debug("task_notify_skipped_priority", task_id=task_id, priority=priority)
        return False

    due_str = f"due {due_at.strftime('%d %b')}" if due_at else "no due date"
    text = (
        f"📋 *New task*\n"
        f"{title}\n"
        f"Priority: {priority} | {due_str}"
    )
    keyboard = [[
        {"text": "✓ Accept",    "callback_data": f"accept:{task_id}"},
        {"text": "✗ Dismiss",   "callback_data": f"dismiss:{task_id}"},
        {"text": "⏰ Snooze 2h", "callback_data": f"snooze:{task_id}"},
    ]]

    try:
        return send_message_with_keyboard(text, keyboard)
    except Exception as exc:
        log.error("task_notify_failed", task_id=task_id, error=str(exc))
        return False
