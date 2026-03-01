# packages/core/src/core/pipeline/reminders.py
from datetime import datetime, timedelta, timezone
from sqlalchemy.exc import IntegrityError
from core.db.engine import get_db
from core.db.models import ActionItem, Reminder, Policy
import structlog

log = structlog.get_logger()

CADENCES: dict[str, list[timedelta]] = {
    "gentle": [timedelta(hours=24), timedelta(hours=4)],
    "standard": [timedelta(hours=48), timedelta(hours=24), timedelta(hours=4)],
    "aggressive": [
        timedelta(hours=72), timedelta(hours=48),
        timedelta(hours=24), timedelta(hours=8), timedelta(hours=4)
    ],
}


def get_policy_cadence(user_id: str) -> str:
    """Get today's reminder cadence from policy. Falls back to 'standard'."""
    today = datetime.now(tz=timezone.utc).date()
    with get_db() as db:
        policy = db.query(Policy).filter_by(user_id=user_id, date=today).first()
        if policy:
            return policy.reminder_cadence
    return "standard"


def schedule_reminders_for_task(task_id: str, cadence: str | None = None) -> int:
    """Create reminder rows for a task based on cadence. Returns count created."""
    with get_db() as db:
        task = db.query(ActionItem).filter_by(id=task_id).first()
        if not task or not task.due_at or task.status in ("done", "dismissed"):
            return 0

        effective_cadence = cadence or get_policy_cadence(task.user_id)
        offsets = CADENCES.get(effective_cadence, CADENCES["standard"])
        count = 0

        for offset in offsets:
            remind_at = task.due_at - offset
            if remind_at <= datetime.now(tz=timezone.utc):
                continue  # Skip past times
            reminder = Reminder(
                action_item_id=task_id,
                user_id=task.user_id,
                remind_at=remind_at,
                channel="cli",
                status="pending",
            )
            db.add(reminder)
            try:
                db.flush()
                count += 1
            except IntegrityError:
                db.rollback()
                # UniqueConstraint(action_item_id, remind_at, channel) — already scheduled

        db.commit()
        log.info("reminders_scheduled", task_id=task_id, cadence=effective_cadence, count=count)
        return count


def _format_reminder_message(task: "ActionItem", reminder: "Reminder") -> str:
    due_str = task.due_at.strftime("%a %b %d %H:%M") if task.due_at else "no due date"
    return (
        f"⏰ *Reminder*\n"
        f"*{task.title}*\n"
        f"Due: {due_str}\n"
        f"{task.details or ''}"
    ).strip()


def dispatch_due_reminders(now: datetime | None = None) -> int:
    """Mark pending reminders as sent and push via Telegram if enabled. Returns count dispatched."""
    from core.telegram_client import send_message  # lazy import to avoid circular deps

    if now is None:
        now = datetime.now(tz=timezone.utc)

    with get_db() as db:
        due = (
            db.query(Reminder)
            .filter(Reminder.status == "pending", Reminder.remind_at <= now)
            .all()
        )
        task_ids = [r.action_item_id for r in due]
        tasks = {
            str(t.id): t
            for t in db.query(ActionItem).filter(ActionItem.id.in_(task_ids)).all()
        }

        count = 0
        for reminder in due:
            reminder.status = "sent"
            reminder.sent_at = now

            task = tasks.get(str(reminder.action_item_id))
            if task:
                msg = _format_reminder_message(task, reminder)
                send_message(msg)  # fail-soft — never raises

            log.info(
                "reminder_dispatched",
                reminder_id=reminder.id,
                action_item_id=reminder.action_item_id,
                channel=reminder.channel,
            )
            count += 1
        db.commit()

    log.info("reminders_dispatch_complete", dispatched=count)
    return count
