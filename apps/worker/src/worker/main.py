# apps/worker/src/worker/main.py
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from worker.jobs import (
    job_poll_and_normalize,
    job_poll_outlook,
    job_poll_gcal,
    job_extract_pending,
    job_schedule_reminders,
    job_daily_pvi_and_digest,
    job_meeting_prep,
)
from core.config import get_settings
import structlog

log = structlog.get_logger()


def start():
    settings = get_settings()
    scheduler = BlockingScheduler()

    scheduler.add_job(job_poll_and_normalize, IntervalTrigger(minutes=2), id="poll_gmail")
    scheduler.add_job(job_poll_outlook, IntervalTrigger(minutes=2), id="poll_outlook")
    scheduler.add_job(job_poll_gcal, IntervalTrigger(minutes=15), id="poll_gcal")
    scheduler.add_job(job_extract_pending, IntervalTrigger(minutes=5), id="extract_pending")
    scheduler.add_job(job_schedule_reminders, IntervalTrigger(minutes=1), id="dispatch_reminders")
    scheduler.add_job(job_meeting_prep, IntervalTrigger(minutes=5), id="meeting_prep")
    scheduler.add_job(job_daily_pvi_and_digest, CronTrigger(hour=7, minute=0), id="daily_pvi_digest")

    log.info("scheduler_starting", jobs=scheduler.get_jobs())
    scheduler.start()


if __name__ == "__main__":
    start()
