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
from core.db.models import ActionItem, Message, Reminder, ReplyDraft
from bot.keyboards import build_snooze_menu

log = structlog.get_logger()


def _send_gmail_reply(draft_text: str, to: str, subject: str, thread_id: str | None) -> bool:
    """Send a Gmail reply. Returns True on success, raises on failure."""
    import base64
    import email.mime.text
    from connectors.gmail.auth import get_credentials
    from googleapiclient.discovery import build

    creds = get_credentials()
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    mime_msg = email.mime.text.MIMEText(draft_text)
    mime_msg["To"] = to
    mime_msg["Subject"] = f"Re: {subject}" if not subject.startswith("Re:") else subject
    if thread_id:
        mime_msg["In-Reply-To"] = thread_id
        mime_msg["References"] = thread_id

    raw = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode()
    service.users().messages().send(
        userId="me",
        body={"raw": raw, "threadId": thread_id},
    ).execute()
    return True


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
    elif action == "done":
        await _done(query, task_id)
    elif action == "snooze":
        await _snooze_menu(query, task_id)
    elif action in ("snooze_1h", "snooze_3h", "snooze_tom"):
        await _snooze_preset(query, action, task_id)
    elif action == "reply_send":
        await _reply_send(query, task_id)
    elif action == "reply_skip":
        await _reply_skip(query, task_id)
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


async def _done(query, task_id: str) -> None:
    try:
        now = datetime.now(timezone.utc)
        with get_db() as db:
            task = db.query(ActionItem).filter_by(id=task_id).first()
            if not task:
                await query.edit_message_text("⚠️ Task not found.")
                return
            title = task.title
            task.status = "done"
            task.updated_at = now
        log.info("task_completed_via_bot", task_id=task_id)
        safe_title = escape_markdown(title, version=2)
        await query.edit_message_text(f"✅ *Done:* {safe_title}", parse_mode="MarkdownV2")
    except Exception:
        log.exception("done_callback_error", task_id=task_id)
        await query.edit_message_text("⚠️ Something went wrong marking that task done.")


async def _snooze_menu(query, task_id: str) -> None:
    """Show snooze duration picker."""
    try:
        with get_db() as db:
            task = db.query(ActionItem).filter_by(id=task_id).first()
            if not task:
                await query.edit_message_text("⚠️ Task not found.")
                return
            title = task.title
        safe_title = escape_markdown(title, version=2)
        from telegram import InlineKeyboardMarkup
        await query.edit_message_text(
            f"⏰ *Snooze until when?*\n_{safe_title}_",
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup(build_snooze_menu(task_id)),
        )
    except Exception:
        log.exception("snooze_menu_error", task_id=task_id)
        await query.edit_message_text("⚠️ Something went wrong.")


async def _snooze_preset(query, action: str, task_id: str) -> None:
    """Handle 1h / 3h / tomorrow morning snooze presets."""
    try:
        from core.config import get_settings
        settings = get_settings()
        now = datetime.now(timezone.utc)

        if action == "snooze_1h":
            remind_at = now + timedelta(hours=1)
            label = "1 hour"
        elif action == "snooze_3h":
            remind_at = now + timedelta(hours=3)
            label = "3 hours"
        else:  # snooze_tom — tomorrow 8am in user's timezone
            try:
                import zoneinfo
                tz = zoneinfo.ZoneInfo(settings.user_timezone or "Asia/Singapore")
                tomorrow = (now.astimezone(tz).date() + timedelta(days=1))
                remind_at = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 8, 0, tzinfo=tz)
            except Exception:
                remind_at = now + timedelta(hours=16)
            label = "tomorrow morning"

        with get_db() as db:
            task = db.query(ActionItem).filter_by(id=task_id).first()
            if not task:
                await query.edit_message_text("⚠️ Task not found.")
                return
            title = task.title
            user_id = str(task.user_id)
            db.add(Reminder(
                action_item_id=task_id,
                user_id=user_id,
                remind_at=remind_at,
                channel="telegram",
                status="pending",
            ))

        log.info("task_snoozed_preset", task_id=task_id, action=action, remind_at=remind_at.isoformat())
        safe_title = escape_markdown(title, version=2)
        safe_label = escape_markdown(label, version=2)
        await query.edit_message_text(
            f"⏰ *Snoozed {safe_label}:* {safe_title}",
            parse_mode="MarkdownV2",
        )
    except Exception:
        log.exception("snooze_preset_error", task_id=task_id, action=action)
        await query.edit_message_text("⚠️ Something went wrong snoozing that task.")


async def _reply_send(query, draft_id: str) -> None:
    try:
        with get_db() as db:
            draft = db.query(ReplyDraft).filter_by(id=draft_id).first()
            if not draft:
                await query.edit_message_text("⚠️ Draft not found.")
                return
            draft_text = draft.draft_text
            message_id = str(draft.message_id)

        with get_db() as db:
            msg = db.query(Message).filter_by(id=message_id).first()
            if not msg:
                await query.edit_message_text("⚠️ Message not found.")
                return
            to = msg.sender
            subject = msg.title
            thread_id = msg.external_id

        _send_gmail_reply(draft_text, to, subject, thread_id)

        with get_db() as db:
            draft = db.query(ReplyDraft).filter_by(id=draft_id).first()
            if draft:
                draft.status = "sent"
        log.info("reply_sent_via_bot", draft_id=draft_id)
        await query.edit_message_text("✓ *Reply sent\\!*", parse_mode="MarkdownV2")
    except Exception:
        log.exception("reply_send_callback_error", draft_id=draft_id)
        await query.edit_message_text("⚠️ Failed to send reply\\. Try `claw reply send` instead\\.", parse_mode="MarkdownV2")


async def _reply_skip(query, draft_id: str) -> None:
    try:
        with get_db() as db:
            draft = db.query(ReplyDraft).filter_by(id=draft_id).first()
            if not draft:
                await query.edit_message_text("⚠️ Draft not found.")
                return
            draft.status = "dismissed"
        log.info("reply_skipped_via_bot", draft_id=draft_id)
        await query.edit_message_text("✗ *Reply skipped*", parse_mode="MarkdownV2")
    except Exception:
        log.exception("reply_skip_callback_error", draft_id=draft_id)
        await query.edit_message_text("⚠️ Something went wrong.")
