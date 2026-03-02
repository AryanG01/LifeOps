# apps/worker/src/worker/jobs.py
from datetime import datetime, timezone

from core.pipeline.normalizer import normalize_all_pending
from core.llm.extractor import extract_all_pending
from core.pipeline.reminders import (
    dispatch_due_reminders,
    schedule_reminders_for_task,
    get_policy_cadence,
)
from core.pvi.engine import compute_pvi_daily
from core.digest.generator import generate_digest
from core.db.engine import get_db
from core.db.models import ActionItem, User
from core.config import get_settings
from core.health import alert
from core.circuit_breaker import llm_breaker
import structlog

log = structlog.get_logger()

# Tracks last successful poll time per source. Used by job_heartbeat().
_last_poll: dict[str, datetime] = {}
_STALE_MINUTES = 30


def job_poll_and_normalize():
    """Poll Gmail for all configured sources and normalize new raw events."""
    try:
        from connectors.gmail.poller import poll_gmail
        with get_db() as db:
            from core.db.models import Source
            sources = db.query(Source).filter_by(source_type="gmail").all()
            source_pairs = [(str(s.user_id), str(s.id)) for s in sources]

        for user_id, source_id in source_pairs:
            poll_gmail(user_id, source_id)

        normalize_all_pending()
        _last_poll["gmail"] = datetime.now(timezone.utc)

    except RuntimeError as exc:
        msg = str(exc).lower()
        if "not connected" in msg or "auth" in msg or "credentials" in msg:
            alert("gmail_auth", "Gmail auth expired. Run: `claw connect gmail`")
        else:
            alert("gmail_poll_error", f"Gmail poll failed: {exc}", level="error")
        log.error("job_poll_gmail_failed", error=str(exc))
    except Exception as exc:
        alert("gmail_poll_error", f"Gmail poll failed: {exc}", level="error")
        log.error("job_poll_gmail_failed", error=str(exc))


def job_extract_pending():
    """Run LLM extraction on all pending messages. Protected by circuit breaker."""
    if llm_breaker.is_open():
        log.info("llm_circuit_open_skipping_extraction")
        return

    _was_failing = llm_breaker._failures > 0 or llm_breaker._tripped_at is not None

    try:
        settings = get_settings()
        success, failed = extract_all_pending(settings.llm_prompt_version)
        log.info("extraction_job_done", success=success, failed=failed)

        if failed > 0 and success == 0:
            # All attempts failed this run
            llm_breaker.record_failure()
            if llm_breaker.is_open():
                alert(
                    "llm_circuit_open",
                    "LLM extraction paused (5 consecutive failures). Will retry in 10 min.",
                    level="error",
                )
        else:
            llm_breaker.record_success()
            if _was_failing:
                alert("llm_circuit_reset", "LLM extraction resumed.", level="info")

    except Exception as exc:
        alert("extract_job_error", f"Extraction job failed: {exc}", level="error")
        log.error("job_extract_failed", error=str(exc))
        llm_breaker.record_failure()
        if llm_breaker.is_open():
            alert(
                "llm_circuit_open",
                "LLM extraction paused (5 consecutive failures). Will retry in 10 min.",
                level="error",
            )


def job_schedule_reminders():
    """Schedule and dispatch due reminders."""
    try:
        with get_db() as db:
            tasks = db.query(ActionItem).filter(
                ActionItem.status.in_(["active", "proposed"]),
                ActionItem.due_at.isnot(None),
            ).all()
            task_pairs = [(str(t.id), str(t.user_id)) for t in tasks]

        for task_id, user_id in task_pairs:
            cadence = get_policy_cadence(user_id)
            schedule_reminders_for_task(task_id, cadence)

        dispatch_due_reminders()

    except Exception as exc:
        alert("reminder_job_error", f"Reminder dispatch failed: {exc}", level="error")
        log.error("job_reminders_failed", error=str(exc))


def job_poll_outlook():
    """Poll Outlook/Exchange via Microsoft Graph delta sync."""
    try:
        from connectors.outlook.poller import poll_outlook
        from core.db.models import Source
        with get_db() as db:
            sources = db.query(Source).filter_by(source_type="outlook").all()
            pairs = [(str(s.user_id), str(s.id)) for s in sources]
        for user_id, source_id in pairs:
            poll_outlook(user_id, source_id)
        _last_poll["outlook"] = datetime.now(timezone.utc)

    except RuntimeError as exc:
        msg = str(exc).lower()
        if "not connected" in msg or "auth" in msg or "credentials" in msg:
            alert("outlook_auth", "Outlook auth expired. Run: `claw connect outlook`")
        else:
            alert("outlook_poll_error", f"Outlook poll failed: {exc}", level="error")
        log.error("job_poll_outlook_failed", error=str(exc))
    except Exception as exc:
        alert("outlook_poll_error", f"Outlook poll failed: {exc}", level="error")
        log.error("job_poll_outlook_failed", error=str(exc))


def job_poll_gcal():
    """Poll Google Calendar for upcoming events."""
    try:
        from connectors.gcal.poller import poll_gcal
        from core.db.models import Source
        with get_db() as db:
            sources = db.query(Source).filter_by(source_type="gcal").all()
            pairs = [(str(s.user_id), str(s.id)) for s in sources]
        for user_id, source_id in pairs:
            poll_gcal(user_id, source_id)
        _last_poll["gcal"] = datetime.now(timezone.utc)

    except Exception as exc:
        alert("gcal_poll_error", f"GCal poll failed: {exc}", level="error")
        log.error("job_poll_gcal_failed", error=str(exc))


def job_meeting_prep():
    """Generate and push meeting prep summaries for upcoming calendar events."""
    try:
        from core.calendar.prep import generate_prep_for_upcoming
        from core.telegram_client import send_message

        settings = get_settings()
        summaries = generate_prep_for_upcoming(settings.default_user_id)
        for msg in summaries:
            send_message(msg)

    except Exception as exc:
        log.error("job_meeting_prep_failed", error=str(exc))


def job_daily_pvi_and_digest():
    """Compute daily PVI score and push digest to Telegram (7am cron)."""
    try:
        from core.telegram_client import send_digest

        with get_db() as db:
            user_ids = [str(u.id) for u in db.query(User).all()]

        for user_id in user_ids:
            compute_pvi_daily(user_id)
            content = generate_digest(user_id)
            sent = send_digest(content)
            log.info("daily_digest_pushed", user_id=user_id, telegram_sent=sent)

    except Exception as exc:
        log.error("job_daily_digest_failed", error=str(exc))


def job_heartbeat():
    """
    Check for stale poll sources. Runs every 5 minutes.
    Fires a Telegram alert if any source hasn't polled in >30 min.
    Only alerts for sources that have polled at least once (_last_poll entry exists).
    """
    now = datetime.now(timezone.utc)
    threshold_seconds = _STALE_MINUTES * 60

    for source, last in list(_last_poll.items()):
        if (now - last).total_seconds() > threshold_seconds:
            alert(
                f"stale_{source}",
                f"No {source.title()} sync in {_STALE_MINUTES}+ min — worker may have crashed.",
                level="warning",
                cooldown_minutes=60,
            )
