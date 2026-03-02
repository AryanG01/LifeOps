"""Meeting prep: detect imminent events and surface relevant context via LLM."""
from datetime import datetime, timezone, timedelta
import structlog

log = structlog.get_logger()


def generate_prep_for_upcoming(user_id: str) -> list[str]:
    """
    Check for events starting in 15-45 minutes.
    For each, generate a 3-bullet prep summary via LLM using related emails.
    Returns list of Telegram-ready message strings.
    """
    from core.db.engine import get_db
    from core.db.models import CalendarEvent, Message
    from core.llm.extractor import _call_llm_raw

    now = datetime.now(tz=timezone.utc)
    window_start = now + timedelta(minutes=15)
    window_end = now + timedelta(minutes=45)

    messages = []

    with get_db() as db:
        upcoming = db.query(CalendarEvent).filter(
            CalendarEvent.user_id == user_id,
            CalendarEvent.start_at >= window_start,
            CalendarEvent.start_at <= window_end,
        ).all()

        for event in upcoming:
            related = db.query(Message).filter(
                Message.user_id == user_id,
                Message.sender.in_(event.attendees_json or []),
            ).order_by(Message.message_ts.desc()).limit(3).all()

            context = "\n".join(
                f"- {m.sender}: {m.title}: {m.body_preview[:100]}"
                for m in related
            ) or "No related emails found."

            prompt = (
                f"Meeting in ~30 minutes: '{event.title}'\n"
                f"Related emails:\n{context}\n\n"
                f"Write a 3-bullet prep summary (what to know, what to prepare, any open questions)."
            )
            try:
                summary = _call_llm_raw("You are a meeting prep assistant.", prompt)
                msg = f"📅 *{event.title}* in 30min\n{summary[:800]}"
                messages.append(msg)
                log.info("meeting_prep_generated", event_id=str(event.id)[:8])
            except Exception as exc:
                log.warning("meeting_prep_failed", error=str(exc))

    return messages
