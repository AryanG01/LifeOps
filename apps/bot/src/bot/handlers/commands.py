# apps/bot/src/bot/handlers/commands.py
"""
Telegram bot command handlers.

Commands:
  /tasks  — list open ActionItems with Accept/Dismiss/Snooze buttons
  /inbox  — last 5 messages with summaries
  /digest — trigger manual digest generation and send
  /pvi    — show today's PVI score
  /focus  — start focus mode (/focus 30 = 30 min)
  /status — system health check
"""
from __future__ import annotations

from datetime import date, datetime, timezone, timedelta

import structlog
from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown

from core.config import get_settings
from core.db.engine import get_db
from core.db.models import (
    ActionItem, Message, MessageSummary, PVIDailyScore, FocusSession, Source, Reminder, ReplyDraft,
)
from bot.keyboards import build_task_keyboard, build_reply_keyboard, build_edit_field_keyboard

log = structlog.get_logger()

# State constants for ConversationHandlers
NEWTASK_TITLE, NEWTASK_DUE = range(2)
SNOOZE_CUSTOM = 20
REPLY_EDIT_TEXT = 10
REPLY_EDIT_CONFIRM = 11
EDIT_CHOOSE_FIELD = 30
EDIT_INPUT_VALUE = 31


def _guard(update: Update) -> bool:
    """Return True if this chat is authorized. False = ignore."""
    settings = get_settings()
    return str(update.effective_chat.id) == str(settings.telegram_chat_id)


def _priority_label(priority: int) -> str:
    if priority >= 70:
        return "🔴 High"
    elif priority >= 40:
        return "🟡 Medium"
    return "🟢 Low"


async def handle_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show open tasks with inline buttons."""
    if not _guard(update):
        return

    settings = get_settings()
    now = datetime.now(timezone.utc)
    with get_db() as db:
        tasks = (
            db.query(ActionItem)
            .filter(
                ActionItem.user_id == settings.default_user_id,
                ActionItem.status.in_(["proposed", "active"]),
            )
            .order_by(ActionItem.priority.desc())
            .limit(10)
            .all()
        )
        task_data = [(str(t.id), t.title, t.priority, t.status, t.due_at) for t in tasks]

    if not task_data:
        await update.message.reply_text("No open tasks.")
        return

    count = len(task_data)
    label = "task" if count == 1 else "tasks"
    await update.message.reply_text(
        f"*You have {count} open {label}:*",
        parse_mode="MarkdownV2",
    )

    tz_name = settings.user_timezone or "Asia/Singapore"
    try:
        import zoneinfo
        user_tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        user_tz = None

    for task_id, title, priority, status, due_at in task_data:
        safe_title = escape_markdown(title, version=2)
        lines = [f"*{safe_title}*"]
        if due_at:
            local_due = due_at.astimezone(user_tz) if user_tz else due_at
            due_str = local_due.strftime("%a %d %b, %H:%M")
            if due_at < now:
                lines.append(f"⚠️ OVERDUE \\(was {escape_markdown(due_str, version=2)}\\)")
            else:
                lines.append(f"⏰ Due: {escape_markdown(due_str, version=2)}")
        lines.append(escape_markdown(_priority_label(priority), version=2))
        await update.message.reply_text(
            "\n".join(lines),
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup(build_task_keyboard(task_id, status)),
        )


async def handle_inbox(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show last 5 messages with summaries."""
    if not _guard(update):
        return

    settings = get_settings()
    with get_db() as db:
        rows = (
            db.query(Message, MessageSummary, Source)
            .outerjoin(MessageSummary, MessageSummary.message_id == Message.id)
            .outerjoin(Source, Source.id == Message.source_id)
            .filter(Message.user_id == settings.default_user_id)
            .order_by(Message.message_ts.desc())
            .limit(5)
            .all()
        )
        lines = []
        for msg, summary, source in rows:
            short = summary.summary_short if summary else "—"
            sender = msg.sender[:30]
            tag = f"\\[{escape_markdown(source.display_name, version=2)}\\] " if source else ""
            lines.append(
                f"* {tag}{escape_markdown(sender, version=2)}: "
                f"{escape_markdown(short[:80], version=2)}"
            )
        inbox_text = "\n".join(lines) if lines else "No messages\\."

    await update.message.reply_text(
        f"*Recent inbox*\n{inbox_text}", parse_mode="MarkdownV2"
    )


async def handle_digest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate and send today's digest."""
    if not _guard(update):
        return

    settings = get_settings()
    await update.message.reply_text("Generating digest...")
    try:
        from core.digest.generator import generate_digest
        from core.telegram_client import send_digest
        content = generate_digest(settings.default_user_id)
        if not content:
            await update.message.reply_text("⚠️ No digest data available for today.")
            return
        send_digest(content)
        await update.message.reply_text("Digest sent.")
    except Exception as exc:
        log.error("bot_digest_failed", error=str(exc))
        await update.message.reply_text(f"Digest failed: {exc}")


async def handle_pvi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show today's PVI score."""
    if not _guard(update):
        return

    settings = get_settings()
    today = date.today()

    with get_db() as db:
        score_row = db.query(PVIDailyScore).filter_by(
            user_id=settings.default_user_id, date=today
        ).first()
        if score_row:
            score_val = score_row.score
            regime = score_row.regime
            explanation = score_row.explanation
        else:
            score_val = None
            regime = None
            explanation = None

    if score_val is None:
        await update.message.reply_text(
            "No PVI score yet for today\\. Run /digest to compute\\.",
            parse_mode="MarkdownV2",
        )
        return

    bar_filled = int(score_val / 10)
    bar = "█" * bar_filled + "░" * (10 - bar_filled)
    safe_regime = escape_markdown(regime, version=2)
    safe_explanation = escape_markdown(explanation, version=2)
    await update.message.reply_text(
        f"*PVI Today: {score_val}* \\({safe_regime}\\)\n{bar}\n_{safe_explanation}_",
        parse_mode="MarkdownV2",
    )


async def handle_focus(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start focus mode. Usage: /focus 30 (minutes)."""
    if not _guard(update):
        return

    settings = get_settings()
    args = context.args
    minutes = 25  # default
    if args:
        try:
            minutes = int(args[0])
            if minutes <= 0:
                await update.message.reply_text(
                    "Usage: /focus 30  \\(minutes must be > 0\\)", parse_mode="MarkdownV2"
                )
                return
        except ValueError:
            await update.message.reply_text(
                "Usage: /focus 30  \\(minutes\\)", parse_mode="MarkdownV2"
            )
            return

    now = datetime.now(timezone.utc)
    ends_at = now + timedelta(minutes=minutes)

    with get_db() as db:
        # End any existing active session
        active = db.query(FocusSession).filter_by(
            user_id=settings.default_user_id, is_active=True
        ).first()
        if active:
            active.is_active = False
            active.ended_early_at = now

        session = FocusSession(
            user_id=settings.default_user_id,
            started_at=now,
            ends_at=ends_at,
            is_active=True,
        )
        db.add(session)
        ends_at_str = ends_at.strftime('%H:%M UTC')

    safe_time = escape_markdown(ends_at_str, version=2)
    await update.message.reply_text(
        f"*Focus mode ON* — {minutes} min\nReminders silenced until {safe_time}",
        parse_mode="MarkdownV2",
    )


async def _create_task_and_reply(update: Update, text: str) -> None:
    """Parse text for a due date, create ActionItem, and send confirmation."""
    settings = get_settings()
    due_at = None
    clean_title = text
    try:
        import re
        from dateparser.search import search_dates
        tz = settings.user_timezone or "Asia/Singapore"
        results = search_dates(
            text,
            settings={"PREFER_DATES_FROM": "future", "TIMEZONE": tz, "RETURN_AS_TIMEZONE_AWARE": True},
        )
        if results:
            date_str, due_at = results[-1]
            clean_title = re.sub(
                rf'\s*(by|due|on|at)\s+{re.escape(date_str)}|\s*{re.escape(date_str)}',
                "", text, flags=re.IGNORECASE,
            ).strip(" ,")
            if not clean_title:
                clean_title = text
    except Exception:
        pass

    with get_db() as db:
        task = ActionItem(
            user_id=settings.default_user_id,
            title=clean_title,
            due_at=due_at,
            status="active",
            priority=50,
            confidence=1.0,
        )
        db.add(task)
        task_id = str(task.id)
        task_title = task.title

        if due_at:
            reminder = Reminder(
                action_item_id=task_id,
                user_id=str(settings.default_user_id),
                remind_at=due_at,
                channel="telegram",
                status="pending",
            )
            db.add(reminder)

    safe_title = escape_markdown(task_title, version=2)
    lines = [f"✅ *{safe_title}*"]
    if due_at:
        try:
            import zoneinfo
            user_tz = zoneinfo.ZoneInfo(settings.user_timezone or "Asia/Singapore")
            local_due = due_at.astimezone(user_tz)
        except Exception:
            local_due = due_at
        due_str = local_due.strftime("%a %d %b, %H:%M")
        lines.append(f"⏰ Due: {escape_markdown(due_str, version=2)}")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup(build_task_keyboard(task_id, "active")),
    )
    log.info("task_created_manually", task_id=task_id, title=task_title, due_at=str(due_at))


async def handle_newtask_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for /newtask. Creates task immediately if args given, else starts conversation."""
    from telegram.ext import ConversationHandler
    if not _guard(update):
        return ConversationHandler.END

    text = " ".join(context.args).strip() if context.args else ""
    if text:
        await _create_task_and_reply(update, text)
        return ConversationHandler.END

    await update.message.reply_text(
        "What's the task? \\(or /cancel to stop\\)", parse_mode="MarkdownV2"
    )
    return NEWTASK_TITLE


async def handle_newtask_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive task title, prompt for due date."""
    from telegram.ext import ConversationHandler
    title = update.message.text.strip()
    if not title:
        await update.message.reply_text("Please enter a task title, or /cancel to stop\\.", parse_mode="MarkdownV2")
        return NEWTASK_TITLE

    context.user_data["newtask_title"] = title
    await update.message.reply_text(
        "When is it due? \\(e\\.g\\. *tomorrow 6pm*, *Friday midnight*, or *skip*\\)",
        parse_mode="MarkdownV2",
    )
    return NEWTASK_DUE


async def handle_newtask_due(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive due date (or 'skip'), create the task."""
    from telegram.ext import ConversationHandler
    due_text = update.message.text.strip()
    title = context.user_data.pop("newtask_title", "")
    if not title:
        await update.message.reply_text(
            "Something went wrong\\. Please try /newtask again\\.", parse_mode="MarkdownV2"
        )
        return ConversationHandler.END

    full_text = f"{title} by {due_text}" if due_text.lower() != "skip" else title
    await _create_task_and_reply(update, full_text)
    return ConversationHandler.END


async def handle_newtask_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the /newtask conversation."""
    from telegram.ext import ConversationHandler
    context.user_data.pop("newtask_title", None)
    await update.message.reply_text("Task creation cancelled\\.", parse_mode="MarkdownV2")
    return ConversationHandler.END


async def handle_replies(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show pending reply drafts with Send / Edit / Skip buttons."""
    if not _guard(update):
        return

    settings = get_settings()
    with get_db() as db:
        rows = (
            db.query(ReplyDraft, Message)
            .join(Message, Message.id == ReplyDraft.message_id)
            .filter(
                Message.user_id == settings.default_user_id,
                ReplyDraft.status == "proposed",
            )
            .order_by(ReplyDraft.created_at.desc())
            .limit(5)
            .all()
        )
        draft_data = [
            (str(d.id), d.draft_text, d.tone, m.sender[:40], m.title[:60])
            for d, m in rows
        ]

    if not draft_data:
        await update.message.reply_text("No pending reply drafts\\.", parse_mode="MarkdownV2")
        return

    count = len(draft_data)
    await update.message.reply_text(
        f"*{count} pending {'draft' if count == 1 else 'drafts'}:*",
        parse_mode="MarkdownV2",
    )

    for draft_id, draft_text, tone, sender, subject in draft_data:
        preview = draft_text[:300] + ("…" if len(draft_text) > 300 else "")
        safe_sender = escape_markdown(sender, version=2)
        safe_subject = escape_markdown(subject, version=2)
        safe_preview = escape_markdown(preview, version=2)
        text = (
            f"📧 *From:* {safe_sender}\n"
            f"*Re:* {safe_subject}\n\n"
            f"_{safe_preview}_"
        )
        from telegram import InlineKeyboardMarkup
        await update.message.reply_text(
            text,
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup(build_reply_keyboard(draft_id)),
        )


async def handle_reply_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point: user tapped ✏️ Edit on a reply draft card."""
    query = update.callback_query
    await query.answer()
    draft_id = query.data.split(":", 1)[1]
    context.user_data["reply_edit_draft_id"] = draft_id

    with get_db() as db:
        draft = db.query(ReplyDraft).filter_by(id=draft_id).first()
        if not draft:
            await query.edit_message_text("⚠️ Draft not found\\.", parse_mode="MarkdownV2")
            from telegram.ext import ConversationHandler
            return ConversationHandler.END
        current_text = draft.draft_text

    safe_current = escape_markdown(current_text, version=2)
    await query.edit_message_text(
        f"✏️ *Edit reply*\n\nCurrent draft:\n_{safe_current}_\n\n"
        "Type your revised reply below, or /cancel",
        parse_mode="MarkdownV2",
    )
    return REPLY_EDIT_TEXT


async def handle_reply_edit_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive revised text, show preview with Confirm / Re-edit / Cancel buttons."""
    new_text = update.message.text.strip()
    context.user_data["reply_edit_new_text"] = new_text

    safe_new = escape_markdown(new_text, version=2)
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    await update.message.reply_text(
        f"*Send this reply?*\n\n_{safe_new}_",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✓ Confirm",  callback_data="reply_edit_confirm"),
            InlineKeyboardButton("↩ Re-edit",  callback_data="reply_edit_redo"),
            InlineKeyboardButton("✗ Cancel",   callback_data="reply_edit_cancel"),
        ]]),
    )
    return REPLY_EDIT_CONFIRM


async def handle_reply_edit_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle Confirm / Re-edit / Cancel on the reply preview."""
    from telegram.ext import ConversationHandler
    query = update.callback_query
    await query.answer()
    action = query.data

    if action == "reply_edit_cancel":
        context.user_data.pop("reply_edit_draft_id", None)
        context.user_data.pop("reply_edit_new_text", None)
        await query.edit_message_text("✗ *Cancelled*", parse_mode="MarkdownV2")
        return ConversationHandler.END

    if action == "reply_edit_redo":
        await query.edit_message_text(
            "Type your revised reply, or /cancel", parse_mode="MarkdownV2"
        )
        return REPLY_EDIT_TEXT

    # Confirm: update draft text and send
    draft_id = context.user_data.pop("reply_edit_draft_id", None)
    new_text = context.user_data.pop("reply_edit_new_text", None)
    if not draft_id or not new_text:
        await query.edit_message_text("⚠️ Session expired\\. Please use /replies again\\.", parse_mode="MarkdownV2")
        return ConversationHandler.END

    try:
        with get_db() as db:
            draft = db.query(ReplyDraft).filter_by(id=draft_id).first()
            if not draft:
                await query.edit_message_text("⚠️ Draft not found\\.", parse_mode="MarkdownV2")
                return ConversationHandler.END
            message_id = str(draft.message_id)
            draft.draft_text = new_text

        with get_db() as db:
            msg = db.query(Message).filter_by(id=message_id).first()
            if not msg:
                await query.edit_message_text("⚠️ Original message not found\\.", parse_mode="MarkdownV2")
                return ConversationHandler.END
            to = msg.sender
            subject = msg.title
            thread_id = msg.external_id

        import base64
        import email.mime.text
        from connectors.gmail.auth import get_credentials
        from googleapiclient.discovery import build as _build
        creds = get_credentials()
        service = _build("gmail", "v1", credentials=creds, cache_discovery=False)
        mime_msg = email.mime.text.MIMEText(new_text)
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

        with get_db() as db:
            draft = db.query(ReplyDraft).filter_by(id=draft_id).first()
            if draft:
                draft.status = "sent"

        log.info("reply_sent_after_edit", draft_id=draft_id)
        await query.edit_message_text("✓ *Reply sent\\!*", parse_mode="MarkdownV2")
    except Exception:
        log.exception("reply_edit_confirm_error", draft_id=draft_id)
        await query.edit_message_text(
            "⚠️ Failed to send reply\\. Try `claw reply send` instead\\.",
            parse_mode="MarkdownV2",
        )
    return ConversationHandler.END


async def handle_reply_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the reply edit conversation."""
    from telegram.ext import ConversationHandler
    context.user_data.pop("reply_edit_draft_id", None)
    context.user_data.pop("reply_edit_new_text", None)
    await update.message.reply_text("Reply editing cancelled\\.", parse_mode="MarkdownV2")
    return ConversationHandler.END


async def handle_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry: user tapped ✏️ Edit on a task card → show field picker."""
    query = update.callback_query
    await query.answer()
    task_id = query.data.split(":", 1)[1]
    context.user_data["edit_task_id"] = task_id

    with get_db() as db:
        task = db.query(ActionItem).filter_by(id=task_id).first()
        if not task:
            await query.edit_message_text("⚠️ Task not found\\.", parse_mode="MarkdownV2")
            from telegram.ext import ConversationHandler
            return ConversationHandler.END
        title = task.title

    safe_title = escape_markdown(title, version=2)
    from telegram import InlineKeyboardMarkup
    await query.edit_message_text(
        f"✏️ *Edit task*\n_{safe_title}_\n\nWhat do you want to change?",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup(build_edit_field_keyboard(task_id)),
    )
    return EDIT_CHOOSE_FIELD


async def handle_edit_field_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User tapped a field button — prompt for the new value."""
    query = update.callback_query
    await query.answer()

    # callback_data: "edit_field:<field>:<task_id>"
    parts = query.data.split(":", 2)
    field = parts[1]
    task_id = parts[2]
    context.user_data["edit_task_id"] = task_id
    context.user_data["edit_field"] = field

    with get_db() as db:
        task = db.query(ActionItem).filter_by(id=task_id).first()
        if not task:
            await query.edit_message_text("⚠️ Task not found\\.", parse_mode="MarkdownV2")
            from telegram.ext import ConversationHandler
            return ConversationHandler.END
        current_title = task.title
        current_due = task.due_at
        current_priority = task.priority

    if field == "title":
        safe_current = escape_markdown(current_title, version=2)
        prompt = f"Current title: _{safe_current}_\n\nType the new title:"
    elif field == "due":
        due_str = current_due.strftime("%a %d %b, %H:%M") if current_due else "not set"
        safe_due = escape_markdown(due_str, version=2)
        prompt = f"Current due date: _{safe_due}_\n\nType the new due date \\(e\\.g\\. *tomorrow 6pm*, *Friday*\\):"
    else:  # priority
        safe_p = escape_markdown(f"{current_priority} ({_priority_label(current_priority)})", version=2)
        prompt = f"Current priority: _{safe_p}_\n\nType new priority: *high*, *medium*, *low*, or a number 0\\-100:"

    await query.edit_message_text(prompt + "\n\nor /cancel", parse_mode="MarkdownV2")
    return EDIT_INPUT_VALUE


async def handle_edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive the new value, update DB, confirm."""
    from telegram.ext import ConversationHandler
    task_id = context.user_data.pop("edit_task_id", None)
    field = context.user_data.pop("edit_field", None)
    value_text = update.message.text.strip()

    if not task_id or not field:
        await update.message.reply_text("Something went wrong\\. Try again\\.", parse_mode="MarkdownV2")
        return ConversationHandler.END

    settings = get_settings()
    tz = settings.user_timezone or "Asia/Singapore"

    with get_db() as db:
        task = db.query(ActionItem).filter_by(id=task_id).first()
        if not task:
            await update.message.reply_text("⚠️ Task not found\\.", parse_mode="MarkdownV2")
            return ConversationHandler.END

        if field == "title":
            task.title = value_text
            confirm = f"✓ Title updated: *{escape_markdown(value_text, version=2)}*"

        elif field == "due":
            try:
                import dateparser
                new_due = dateparser.parse(
                    value_text,
                    settings={"PREFER_DATES_FROM": "future", "TIMEZONE": tz, "RETURN_AS_TIMEZONE_AWARE": True},
                )
            except Exception:
                new_due = None

            if not new_due:
                await update.message.reply_text(
                    "Couldn't parse that date\\. Try *tomorrow 6pm* or *Friday*\\.",
                    parse_mode="MarkdownV2",
                )
                context.user_data["edit_task_id"] = task_id
                context.user_data["edit_field"] = field
                return EDIT_INPUT_VALUE

            task.due_at = new_due
            try:
                import zoneinfo
                local = new_due.astimezone(zoneinfo.ZoneInfo(tz))
            except Exception:
                local = new_due
            due_str = local.strftime("%a %d %b, %H:%M")
            confirm = f"✓ Due date updated: *{escape_markdown(due_str, version=2)}*"

        else:  # priority
            priority_map = {"high": 80, "medium": 50, "low": 20}
            norm = value_text.lower().strip()
            if norm in priority_map:
                new_priority = priority_map[norm]
            else:
                try:
                    new_priority = int(norm)
                    if not (0 <= new_priority <= 100):
                        raise ValueError
                except ValueError:
                    await update.message.reply_text(
                        "Invalid priority\\. Use *high*, *medium*, *low*, or a number 0\\-100\\.",
                        parse_mode="MarkdownV2",
                    )
                    context.user_data["edit_task_id"] = task_id
                    context.user_data["edit_field"] = field
                    return EDIT_INPUT_VALUE

            task.priority = new_priority
            confirm = f"✓ Priority updated: *{escape_markdown(_priority_label(new_priority), version=2)}*"

        task.updated_at = datetime.now(timezone.utc)
        updated_title = task.title
        updated_priority = task.priority
        updated_status = task.status
        updated_due = task.due_at

    log.info("task_edited_via_bot", task_id=task_id, field=field)

    # Confirm + re-render task card
    from telegram import InlineKeyboardMarkup
    await update.message.reply_text(confirm, parse_mode="MarkdownV2")

    safe_title = escape_markdown(updated_title, version=2)
    lines = [f"*{safe_title}*"]
    now = datetime.now(timezone.utc)
    if updated_due:
        try:
            import zoneinfo
            local_due = updated_due.astimezone(zoneinfo.ZoneInfo(tz))
        except Exception:
            local_due = updated_due
        due_str = local_due.strftime("%a %d %b, %H:%M")
        if updated_due < now:
            lines.append(f"⚠️ OVERDUE \\(was {escape_markdown(due_str, version=2)}\\)")
        else:
            lines.append(f"⏰ Due: {escape_markdown(due_str, version=2)}")
    lines.append(escape_markdown(_priority_label(updated_priority), version=2))
    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup(build_task_keyboard(task_id, updated_status)),
    )
    return ConversationHandler.END


async def handle_edit_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel task editing."""
    from telegram.ext import ConversationHandler
    context.user_data.pop("edit_task_id", None)
    context.user_data.pop("edit_field", None)
    await update.message.reply_text("Edit cancelled\\.", parse_mode="MarkdownV2")
    return ConversationHandler.END


async def handle_snooze_custom_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point: user tapped 'Custom ✏️' on the snooze menu."""
    query = update.callback_query
    await query.answer()
    task_id = query.data.split(":", 1)[1]
    context.user_data["snooze_task_id"] = task_id
    await query.edit_message_text(
        "⏰ *When should I remind you?*\n\n"
        "_Examples: tomorrow 8am, Friday 5pm, 6h_\n\n"
        "or /cancel",
        parse_mode="MarkdownV2",
    )
    return SNOOZE_CUSTOM


async def handle_snooze_custom_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive natural language time, create reminder."""
    from telegram.ext import ConversationHandler
    task_id = context.user_data.pop("snooze_task_id", None)
    if not task_id:
        await update.message.reply_text("Something went wrong\\. Try again\\.", parse_mode="MarkdownV2")
        return ConversationHandler.END

    text = update.message.text.strip()
    settings = get_settings()
    tz = settings.user_timezone or "Asia/Singapore"

    remind_at = None
    try:
        import dateparser
        remind_at = dateparser.parse(
            text,
            settings={"PREFER_DATES_FROM": "future", "TIMEZONE": tz, "RETURN_AS_TIMEZONE_AWARE": True},
        )
    except Exception:
        pass

    if not remind_at:
        await update.message.reply_text(
            "Couldn't parse that time\\. Try something like *tomorrow 8am* or *Friday 5pm*\\.",
            parse_mode="MarkdownV2",
        )
        return SNOOZE_CUSTOM  # stay in state, let user retry

    with get_db() as db:
        task = db.query(ActionItem).filter_by(id=task_id).first()
        if not task:
            await update.message.reply_text("⚠️ Task not found\\.", parse_mode="MarkdownV2")
            return ConversationHandler.END
        title = task.title
        user_id = str(task.user_id)
        db.add(Reminder(
            action_item_id=task_id,
            user_id=user_id,
            remind_at=remind_at,
            channel="telegram",
            status="pending",
        ))

    log.info("task_snoozed_custom", task_id=task_id, remind_at=remind_at.isoformat())
    try:
        import zoneinfo
        local = remind_at.astimezone(zoneinfo.ZoneInfo(tz))
    except Exception:
        local = remind_at
    time_str = local.strftime("%a %d %b, %H:%M")
    safe_title = escape_markdown(title, version=2)
    safe_time = escape_markdown(time_str, version=2)
    await update.message.reply_text(
        f"⏰ *Snoozed:* {safe_title}\nI'll remind you at {safe_time}",
        parse_mode="MarkdownV2",
    )
    return ConversationHandler.END


async def handle_snooze_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the custom snooze conversation."""
    from telegram.ext import ConversationHandler
    context.user_data.pop("snooze_task_id", None)
    await update.message.reply_text("Snooze cancelled\\.", parse_mode="MarkdownV2")
    return ConversationHandler.END


async def handle_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Search tasks and messages. Usage: /search <query>"""
    if not _guard(update):
        return

    query_text = " ".join(context.args).strip() if context.args else ""
    if not query_text:
        await update.message.reply_text(
            "Usage: `/search <query>`", parse_mode="MarkdownV2"
        )
        return

    settings = get_settings()
    pattern = f"%{query_text}%"

    with get_db() as db:
        tasks = (
            db.query(ActionItem)
            .filter(
                ActionItem.user_id == settings.default_user_id,
                ActionItem.status.in_(["proposed", "active"]),
                ActionItem.title.ilike(pattern),
            )
            .order_by(ActionItem.priority.desc())
            .limit(5)
            .all()
        )
        task_data = [(str(t.id), t.title, t.priority, t.status, t.due_at) for t in tasks]

        msgs = (
            db.query(Message)
            .filter(
                Message.user_id == settings.default_user_id,
                (
                    Message.sender.ilike(pattern)
                    | Message.title.ilike(pattern)
                    | Message.body_preview.ilike(pattern)
                ),
            )
            .order_by(Message.message_ts.desc())
            .limit(5)
            .all()
        )
        msg_data = [(m.sender[:40], m.title[:60]) for m in msgs]

    safe_q = escape_markdown(query_text, version=2)
    header = f"🔍 *Results for \"{safe_q}\"*\n"

    if not task_data and not msg_data:
        await update.message.reply_text(
            f"{header}\nNo results found\\.", parse_mode="MarkdownV2"
        )
        return

    # Send header
    await update.message.reply_text(header, parse_mode="MarkdownV2")

    # Send task cards (reuse the same task card format as /tasks)
    now = datetime.now(timezone.utc)
    tz_name = settings.user_timezone or "Asia/Singapore"
    try:
        import zoneinfo
        user_tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        user_tz = None

    for task_id, title, priority, status, due_at in task_data:
        safe_title = escape_markdown(title, version=2)
        lines = [f"*{safe_title}*"]
        if due_at:
            local_due = due_at.astimezone(user_tz) if user_tz else due_at
            due_str = local_due.strftime("%a %d %b, %H:%M")
            if due_at < now:
                lines.append(f"⚠️ OVERDUE \\(was {escape_markdown(due_str, version=2)}\\)")
            else:
                lines.append(f"⏰ Due: {escape_markdown(due_str, version=2)}")
        lines.append(escape_markdown(_priority_label(priority), version=2))
        from telegram import InlineKeyboardMarkup
        await update.message.reply_text(
            "\n".join(lines),
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup(build_task_keyboard(task_id, status)),
        )

    # Send message results as plain text
    if msg_data:
        msg_lines = [f"*📬 Messages \\({len(msg_data)}\\)*"]
        for sender, title in msg_data:
            msg_lines.append(
                f"• {escape_markdown(sender, version=2)}: {escape_markdown(title, version=2)}"
            )
        await update.message.reply_text("\n".join(msg_lines), parse_mode="MarkdownV2")


async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show system status: DB health, telegram, circuit breaker."""
    if not _guard(update):
        return

    lines = ["*Clawdbot Status*\n"]

    # DB check
    try:
        from core.db.models import User
        with get_db() as db:
            count = db.query(User).count()
        lines.append(f"DB: connected \\({count} users\\)")
    except Exception as exc:
        safe_exc = escape_markdown(str(exc)[:100], version=2)
        lines.append(f"DB error: {safe_exc}")

    # Circuit breaker
    try:
        from core.circuit_breaker import llm_breaker
        is_open = llm_breaker.is_open()
        status_text = "open \\(paused\\)" if is_open else "closed \\(OK\\)"
        lines.append(f"LLM circuit: {status_text}")
    except Exception:
        lines.append("LLM circuit: unknown")

    # Telegram
    lines.append("Telegram: connected \\(you're reading this\\!\\)")

    await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2")
