# apps/bot/src/bot/handlers/callbacks.py
"""
Telegram inline keyboard callback handler.

Callback data format: "action:task_uuid"
  - accept:uuid   → ActionItem.status = "active"
  - dismiss:uuid  → ActionItem.status = "dismissed"
  - snooze:uuid   → Reminder added for now + 2h
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import structlog
from telegram import Update
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown

from core.config import get_settings
from core.db.engine import get_db
from core.db.models import ActionItem, Reminder

log = structlog.get_logger()

_SNOOZE_HOURS = 2


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route accept/dismiss/snooze callback queries."""
    settings = get_settings()
    query = update.callback_query

    # Security guard: only respond to the configured owner's chat
    if str(update.effective_chat.id) != str(settings.telegram_chat_id):
        log.warning("callback_wrong_chat", chat_id=update.effective_chat.id)
        return

    await query.answer()  # removes the "loading" spinner on the button

    data: str | None = query.data
    if not data:
        await query.edit_message_text("⚠️ Unknown action.")
        return

    parts = data.split(":", 1)
    if len(parts) != 2:
        await query.edit_message_text("⚠️ Unknown action.")
        return

    action, task_id = parts

    if action == "accept":
        await _accept(query, task_id)
    elif action == "dismiss":
        await _dismiss(query, task_id)
    elif action == "snooze":
        await _snooze(query, task_id)
    else:
        await query.edit_message_text("⚠️ Unknown action.")


async def _accept(query, task_id: str) -> None:
    try:
        now = datetime.now(timezone.utc)
        with get_db() as db:
            task = db.query(ActionItem).filter_by(id=task_id).first()
            if not task:
                await query.edit_message_text("⚠️ Task not found.")
                return
            title = task.title
            task.status = "active"
            task.updated_at = now
        log.info("task_accepted_via_bot", task_id=task_id)
        safe_title = escape_markdown(title, version=2)
        await query.edit_message_text(f"✓ *Accepted:* {safe_title}", parse_mode="MarkdownV2")
    except Exception:
        log.exception("accept_callback_error", task_id=task_id)
        await query.edit_message_text("⚠️ Something went wrong accepting that task.")


async def _dismiss(query, task_id: str) -> None:
    try:
        now = datetime.now(timezone.utc)
        with get_db() as db:
            task = db.query(ActionItem).filter_by(id=task_id).first()
            if not task:
                await query.edit_message_text("⚠️ Task not found.")
                return
            title = task.title
            task.status = "dismissed"
            task.updated_at = now
        log.info("task_dismissed_via_bot", task_id=task_id)
        safe_title = escape_markdown(title, version=2)
        await query.edit_message_text(f"✗ *Dismissed:* {safe_title}", parse_mode="MarkdownV2")
    except Exception:
        log.exception("dismiss_callback_error", task_id=task_id)
        await query.edit_message_text("⚠️ Something went wrong dismissing that task.")


async def _snooze(query, task_id: str) -> None:
    try:
        now = datetime.now(timezone.utc)
        remind_at = now + timedelta(hours=_SNOOZE_HOURS)
        with get_db() as db:
            task = db.query(ActionItem).filter_by(id=task_id).first()
            if not task:
                await query.edit_message_text("⚠️ Task not found.")
                return
            title = task.title
            user_id = str(task.user_id)
            reminder = Reminder(
                action_item_id=task_id,
                user_id=user_id,
                remind_at=remind_at,
                channel="telegram",
                status="pending",
            )
            db.add(reminder)
        log.info("task_snoozed_via_bot", task_id=task_id, remind_at=remind_at.isoformat())
        safe_title = escape_markdown(title, version=2)
        time_str = escape_markdown(remind_at.strftime('%H:%M UTC'), version=2)
        await query.edit_message_text(
            f"⏰ *Snoozed 2h:* {safe_title}\nI'll remind you at {time_str}",
            parse_mode="MarkdownV2",
        )
    except Exception:
        log.exception("snooze_callback_error", task_id=task_id)
        await query.edit_message_text("⚠️ Something went wrong snoozing that task.")
