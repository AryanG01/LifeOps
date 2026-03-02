# packages/core/src/core/telegram_client.py
"""
Lightweight Telegram Bot API client using httpx.

Usage:
    from core.telegram_client import send_message
    send_message("Hello from Clawdbot!")
"""
import httpx
import structlog
from core.config import get_settings

log = structlog.get_logger()

_BASE = "https://api.telegram.org/bot{token}/sendMessage"


def send_message(text: str, parse_mode: str = "Markdown") -> bool:
    """
    Send a message to the configured Telegram chat.
    Returns True on success, False on failure (fail-soft).
    Never raises — callers should not crash on Telegram errors.
    """
    settings = get_settings()
    if not settings.telegram_enabled:
        log.debug("telegram_disabled_skipping")
        return False
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        log.warning("telegram_not_configured")
        return False

    url = _BASE.format(token=settings.telegram_bot_token)
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }

    try:
        response = httpx.post(url, json=payload, timeout=10)
        response.raise_for_status()
        log.info("telegram_sent", chat_id=settings.telegram_chat_id,
                 chars=len(text))
        return True
    except httpx.HTTPStatusError as exc:
        log.error("telegram_http_error", status=exc.response.status_code,
                  body=exc.response.text[:200])
        return False
    except Exception as exc:
        log.error("telegram_error", error=str(exc))
        return False


def send_message_with_keyboard(
    text: str,
    keyboard: list[list[dict]],
    parse_mode: str = "Markdown",
) -> bool:
    """
    Send a message with an inline keyboard.

    keyboard format:
        [[{"text": "✓ Accept", "callback_data": "accept:uuid"}, ...], ...]
    Each inner list is one row of buttons.
    Returns True on success, False on failure. Never raises.
    """
    settings = get_settings()
    if not settings.telegram_enabled:
        log.debug("telegram_disabled_skipping")
        return False
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        log.warning("telegram_not_configured")
        return False

    url = _BASE.format(token=settings.telegram_bot_token)
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "reply_markup": {"inline_keyboard": keyboard},
    }

    try:
        response = httpx.post(url, json=payload, timeout=10)
        response.raise_for_status()
        log.info("telegram_keyboard_sent", chat_id=settings.telegram_chat_id)
        return True
    except httpx.HTTPStatusError as exc:
        log.error("telegram_http_error", status=exc.response.status_code,
                  body=exc.response.text[:200])
        return False
    except Exception as exc:
        log.error("telegram_error", error=str(exc))
        return False


def send_digest(content_md: str) -> bool:
    """Send a digest (Markdown) to Telegram, chunking if needed (4096 char limit)."""
    LIMIT = 4096
    if len(content_md) <= LIMIT:
        return send_message(content_md)

    # Split on double newlines, respecting the Telegram limit
    chunks: list[str] = []
    current = ""
    for paragraph in content_md.split("\n\n"):
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) > LIMIT:
            if current:
                chunks.append(current)
            current = paragraph[:LIMIT]
        else:
            current = candidate
    if current:
        chunks.append(current)

    success = True
    for i, chunk in enumerate(chunks):
        ok = send_message(chunk)
        if not ok:
            log.error("telegram_chunk_failed", chunk_index=i, total=len(chunks))
            success = False
    return success
