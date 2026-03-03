# packages/core/src/core/reply_notify.py
"""
Push an immediate reply-draft notification to Telegram when an LLM ReplyDraft is created.

Called by extractor.py after successful commit.
Fail-soft: never raises, never blocks extraction.
"""
from __future__ import annotations

import structlog

from core.config import get_settings
from core.telegram_client import send_message, send_message_with_keyboard

log = structlog.get_logger()

_PREVIEW_MAX = 200


def send_reply_notification(
    draft_id: str,
    message_id: str,
    sender: str,
    subject: str,
    preview: str,
) -> bool:
    """
    Push a reply-draft notification to Telegram.

    Returns True on success, False if skipped or failed. Never raises.

    Args:
        draft_id: ReplyDraft UUID (for callback routing).
        message_id: Message UUID (for logging only).
        sender: Original email sender address.
        subject: Email subject.
        preview: First N chars of draft text.
    """
    settings = get_settings()
    if not settings.telegram_enabled:
        return False

    truncated = preview[:_PREVIEW_MAX] + ("…" if len(preview) > _PREVIEW_MAX else "")
    text = (
        f"✉️ *Reply draft ready*\n"
        f"From: {sender}\n"
        f"Re: {subject}\n\n"
        f"_{truncated}_"
    )

    keyboard = [[
        {"text": "✉️ Send", "callback_data": f"reply_send:{draft_id}"},
        {"text": "✗ Skip", "callback_data": f"reply_skip:{draft_id}"},
    ]]

    try:
        return send_message_with_keyboard(text, keyboard)
    except Exception as exc:
        log.error("reply_notify_failed", draft_id=draft_id, message_id=message_id,
                  error=str(exc), exc_info=True)
        return False
