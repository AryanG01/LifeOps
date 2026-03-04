# packages/core/src/core/digest/generator.py
from datetime import datetime, timedelta, date, timezone
from sqlalchemy import or_
from core.db.engine import get_db
from core.db.models import ActionItem, Message, MessageSummary, Policy, Digest, PVIDailyScore
import structlog

log = structlog.get_logger()


def _pri_icon(priority: int) -> str:
    if priority >= 70:
        return "🔴"
    elif priority >= 40:
        return "🟡"
    return "🟢"


def generate_digest(user_id: str, for_date: date | None = None) -> str:
    if for_date is None:
        for_date = datetime.now(tz=timezone.utc).date()

    now_utc = datetime.now(tz=timezone.utc)
    day_end = datetime.combine(for_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    week_end = day_end + timedelta(days=7)

    with get_db() as db:
        policy = db.query(Policy).filter_by(user_id=user_id, date=for_date).first()
        max_items = policy.max_digest_items if policy else 15
        regime = policy.regime if policy else "normal"

        pvi = db.query(PVIDailyScore).filter_by(user_id=user_id, date=for_date).first()

        do_today = db.query(ActionItem).filter(
            ActionItem.user_id == user_id,
            ActionItem.status.in_(["proposed", "active"]),
            ActionItem.due_at <= day_end,
            ActionItem.due_at >= now_utc,
        ).order_by(ActionItem.priority.desc()).limit(max_items).all()

        upcoming = db.query(ActionItem).filter(
            ActionItem.user_id == user_id,
            ActionItem.status.in_(["proposed", "active"]),
            ActionItem.due_at > day_end,
            ActionItem.due_at <= week_end,
        ).order_by(ActionItem.due_at, ActionItem.priority.desc()).limit(max_items).all()

        recent_messages = db.query(Message, MessageSummary).join(
            MessageSummary, MessageSummary.message_id == Message.id, isouter=True
        ).filter(
            Message.user_id == user_id,
            Message.ingested_at >= now_utc - timedelta(days=1),
            or_(
                MessageSummary.id.is_(None),
                MessageSummary.summary_short != "triage:skip",
            ),
        ).order_by(Message.message_ts.desc()).limit(max_items).all()

        date_str = for_date.strftime("%a %d %b")
        lines = [f"*Clawdbot Digest — {date_str}*"]
        if pvi:
            lines.append(f"Policy: {regime} | PVI: {pvi.score} ({pvi.regime})")
        else:
            lines.append(f"Policy: {regime}")
        lines.append("")

        lines.append("*📋 DO TODAY*")
        if do_today:
            for task in do_today:
                icon = _pri_icon(task.priority)
                due_part = f" _(due {task.due_at.strftime('%a %d %b, %H:%M')})_" if task.due_at else ""
                lines.append(f"{icon} {task.title}{due_part}")
        else:
            lines.append("_Nothing due today_")

        lines.append("")
        lines.append("*📅 UPCOMING*")
        if upcoming:
            for task in upcoming:
                icon = _pri_icon(task.priority)
                due_part = f" _(due {task.due_at.strftime('%a %d %b, %H:%M')})_" if task.due_at else ""
                lines.append(f"{icon} {task.title}{due_part}")
        else:
            lines.append("_Nothing in the next 7 days_")

        lines.append("")
        lines.append("*📬 UPDATES*")
        if recent_messages:
            for msg, summary in recent_messages:
                short = summary.summary_short if summary else msg.body_preview[:80]
                canvas_tag = " [Canvas]" if msg.is_canvas else ""
                lines.append(f"• {msg.sender[:30]}{canvas_tag}: {short}")
        else:
            lines.append("_No recent updates_")

        if pvi:
            bar_filled = int(pvi.score / 10)
            bar = "▓" * bar_filled + "░" * (10 - bar_filled)
            lines.append("")
            lines.append(f"*📊 PVI Score: {pvi.score}* ({pvi.regime})")
            lines.append(bar)
            lines.append(f"_{pvi.explanation}_")

        content = "\n".join(lines)

        existing = db.query(Digest).filter_by(user_id=user_id, date=for_date).first()
        if existing:
            existing.content_md = content
            existing.regime = regime
            existing.generated_at = now_utc
        else:
            db.add(Digest(user_id=user_id, date=for_date, content_md=content, regime=regime))
        db.commit()

    log.info("digest_generated", user_id=user_id, date=str(for_date))
    return content
