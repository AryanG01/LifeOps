# apps/worker/src/worker/jobs.py
from core.pipeline.normalizer import normalize_all_pending
from core.llm.extractor import extract_all_pending
from core.pipeline.reminders import dispatch_due_reminders, schedule_reminders_for_task, get_policy_cadence
from core.pvi.engine import compute_pvi_daily
from core.digest.generator import generate_digest
from core.db.engine import get_db
from core.db.models import ActionItem, User
from core.config import get_settings
import structlog

log = structlog.get_logger()


def job_poll_and_normalize():
    """Poll Gmail for all configured sources and normalize new raw events."""
    from connectors.gmail.poller import poll_gmail
    with get_db() as db:
        from core.db.models import Source
        sources = db.query(Source).filter_by(source_type="gmail").all()
        source_pairs = [(str(s.user_id), str(s.id)) for s in sources]

    for user_id, source_id in source_pairs:
        poll_gmail(user_id, source_id)

    normalize_all_pending()


def job_extract_pending():
    settings = get_settings()
    success, failed = extract_all_pending(settings.llm_prompt_version)
    log.info("extraction_job_done", success=success, failed=failed)


def job_schedule_reminders():
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


def job_daily_pvi_and_digest():
    from core.telegram_client import send_digest

    with get_db() as db:
        user_ids = [str(u.id) for u in db.query(User).all()]

    for user_id in user_ids:
        compute_pvi_daily(user_id)
        content = generate_digest(user_id)
        sent = send_digest(content)
        log.info("daily_digest_pushed", user_id=user_id, telegram_sent=sent)
