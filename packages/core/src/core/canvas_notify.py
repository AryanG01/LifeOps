# packages/core/src/core/canvas_notify.py
"""
Push an immediate Canvas notification to Telegram when a Canvas email is detected.

Called by normalize_raw_event() after successful commit.
Fail-soft: never raises, never blocks normalization.
"""
from __future__ import annotations

import structlog

from connectors.canvas.parser import CanvasParseResult
from core.config import get_settings
from core.telegram_client import send_message, send_message_with_keyboard

log = structlog.get_logger()

_TYPE_EMOJI = {
    "assignment":   "📋",
    "announcement": "📢",
    "quiz":         "📝",
    "grade":        "🏆",
}


def send_canvas_notification(canvas: CanvasParseResult, msg_id: str) -> bool:
    """
    Push a Canvas notification to Telegram.

    Returns True on success, False if skipped or failed. Never raises.

    Args:
        canvas: Parsed Canvas result (is_canvas=True assumed).
        msg_id: Message UUID (for logging).
    """
    settings = get_settings()
    if not settings.telegram_enabled:
        return False

    emoji = _TYPE_EMOJI.get(canvas.canvas_type or "", "📚")
    course = canvas.course_code or "Canvas"
    title = canvas.assignment_title or "New notification"
    canvas_type_label = (canvas.canvas_type or "notification").capitalize()

    lines = [f"{emoji} *{canvas_type_label}* — {course}", title]
    if canvas.due_at_raw:
        lines.append(f"Due: {canvas.due_at_raw}")
    text = "\n".join(lines)

    try:
        if canvas.canvas_url:
            keyboard = [[{"text": "View on Canvas", "url": canvas.canvas_url}]]
            return send_message_with_keyboard(text, keyboard)
        return send_message(text)
    except Exception as exc:
        log.error("canvas_notify_failed", msg_id=msg_id, error=str(exc))
        return False
