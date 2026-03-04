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
    ActionItem, Message, MessageSummary, PVIDailyScore, FocusSession,
)
from bot.keyboards import build_task_keyboard

log = structlog.get_logger()


def _guard(update: Update) -> bool:
    """Return True if this chat is authorized. False = ignore."""
    settings = get_settings()
    return str(update.effective_chat.id) == str(settings.telegram_chat_id)


async def handle_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show open tasks with inline buttons."""
    if not _guard(update):
        return

    settings = get_settings()
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
        # Extract all data inside the session
        task_data = [(str(t.id), t.title, t.priority) for t in tasks]

    if not task_data:
        await update.message.reply_text("No open tasks.")
        return

    for task_id, title, priority in task_data:
        safe_title = escape_markdown(title, version=2)
        await update.message.reply_text(
            f"*{safe_title}*\nPriority: {priority}",
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup(build_task_keyboard(task_id)),
        )


async def handle_inbox(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show last 5 messages with summaries."""
    if not _guard(update):
        return

    settings = get_settings()
    with get_db() as db:
        messages = (
            db.query(Message)
            .filter_by(user_id=settings.default_user_id)
            .order_by(Message.message_ts.desc())
            .limit(5)
            .all()
        )
        lines = []
        for msg in messages:
            summary = db.query(MessageSummary).filter_by(
                message_id=str(msg.id)
            ).first()
            short = summary.summary_short if summary else "—"
            # Truncate and escape for safe display
            sender = msg.sender[:30]
            lines.append(
                f"* {escape_markdown(sender, version=2)}: "
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


async def handle_newtask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Create a task manually. Usage: /newtask Buy groceries by tomorrow 6pm"""
    if not _guard(update):
        return

    text = " ".join(context.args).strip() if context.args else ""
    if not text:
        await update.message.reply_text(
            "Usage: `/newtask <title>`\nExample: `/newtask Submit CS2103 report by Friday`",
            parse_mode="MarkdownV2",
        )
        return

    settings = get_settings()
    with get_db() as db:
        from core.db.models import ActionItem
        task = ActionItem(
            user_id=settings.default_user_id,
            title=text,
            status="active",
            priority=50,
            confidence=1.0,
        )
        db.add(task)
        task_id = str(task.id)
        task_title = task.title

    safe_title = escape_markdown(task_title, version=2)
    await update.message.reply_text(
        f"✅ Task created: *{safe_title}*",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup(build_task_keyboard(task_id)),
    )
    log.info("task_created_manually", task_id=task_id, title=task_title)


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
