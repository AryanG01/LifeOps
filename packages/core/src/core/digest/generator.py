# packages/core/src/core/digest/generator.py
from datetime import datetime, timedelta, date, timezone
from sqlalchemy import or_
from core.db.engine import get_db
from core.db.models import ActionItem, Message, MessageSummary, Policy, Digest, PVIDailyScore
import structlog

log = structlog.get_logger()


def generate_digest(user_id: str, for_date: date | None = None) -> str:
    if for_date is None:
        for_date = datetime.now(tz=timezone.utc).date()

    now = datetime.combine(for_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    day_end = now
    week_end = now + timedelta(days=7)

    with get_db() as db:
        # Get policy
        policy = db.query(Policy).filter_by(user_id=user_id, date=for_date).first()
        max_items = policy.max_digest_items if policy else 15
        regime = policy.regime if policy else "normal"

        # Get PVI score
        pvi = db.query(PVIDailyScore).filter_by(user_id=user_id, date=for_date).first()

        # Do today: active/proposed tasks due within 24h
        do_today = db.query(ActionItem).filter(
            ActionItem.user_id == user_id,
            ActionItem.status.in_(["proposed", "active"]),
            ActionItem.due_at <= day_end,
            ActionItem.due_at >= datetime.now(tz=timezone.utc),
        ).order_by(ActionItem.priority.desc()).limit(max_items).all()

        # Upcoming: due within 7 days
        upcoming = db.query(ActionItem).filter(
            ActionItem.user_id == user_id,
            ActionItem.status.in_(["proposed", "active"]),
            ActionItem.due_at > day_end,
            ActionItem.due_at <= week_end,
        ).order_by(ActionItem.due_at, ActionItem.priority.desc()).limit(max_items).all()

        # Recent messages (announcements/updates) — exclude triage-skipped newsletters/promos
        recent_messages = db.query(Message, MessageSummary).join(
            MessageSummary, MessageSummary.message_id == Message.id, isouter=True
        ).filter(
            Message.user_id == user_id,
            Message.ingested_at >= datetime.now(tz=timezone.utc) - timedelta(days=1),
            or_(
                MessageSummary.id.is_(None),
                MessageSummary.summary_short != "triage:skip",
            ),
        ).order_by(Message.message_ts.desc()).limit(max_items).all()

        lines = [f"# Clawdbot Digest — {for_date} (Policy: {regime}, max {max_items})", ""]

        lines.append("## DO TODAY")
        if do_today:
            for task in do_today:
                due_str = task.due_at.strftime("%Y-%m-%d %H:%M") if task.due_at else "no due date"
                lines.append(f"- [ ] {task.title} (due {due_str}) [priority {task.priority}]")
                if task.details:
                    lines.append(f"  {task.details}")
        else:
            lines.append("_Nothing due today_")

        lines += ["", "## UPCOMING"]
        if upcoming:
            for task in upcoming:
                due_str = task.due_at.strftime("%Y-%m-%d %H:%M") if task.due_at else "no due date"
                lines.append(
                    f"- [ ] {task.title} (due {due_str})"
                    f" [priority {task.priority}; conf {task.confidence:.2f}]"
                )
        else:
            lines.append("_Nothing in the next 7 days_")

        lines += ["", "## UPDATES"]
        if recent_messages:
            for msg, summary in recent_messages:
                short = summary.summary_short if summary else msg.body_preview[:80]
                canvas_tag = " [Canvas]" if msg.is_canvas else ""
                lines.append(f"- {msg.sender}{canvas_tag}: {short}")
        else:
            lines.append("_No recent updates_")

        if pvi:
            lines += ["", "## PVI"]
            lines.append(f"- Score: {pvi.score} ({pvi.regime})")
            lines.append(f"- Drivers: {pvi.explanation}")

        content = "\n".join(lines)

        # Upsert digest
        existing = db.query(Digest).filter_by(user_id=user_id, date=for_date).first()
        if existing:
            existing.content_md = content
            existing.regime = regime
            existing.generated_at = datetime.now(tz=timezone.utc)
        else:
            db.add(Digest(user_id=user_id, date=for_date, content_md=content, regime=regime))
        db.commit()

    log.info("digest_generated", user_id=user_id, date=str(for_date))
    return content
