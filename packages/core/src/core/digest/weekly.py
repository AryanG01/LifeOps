"""Weekly review digest — summary of the past 7 days."""
from datetime import datetime, timezone, timedelta
import structlog

log = structlog.get_logger()


def generate_weekly_review(user_id: str) -> str:
    from core.db.engine import get_db
    from core.db.models import ActionItem, PVIDailyScore, Message

    now = datetime.now(tz=timezone.utc)
    week_ago = now - timedelta(days=7)
    today = now.date()

    with get_db() as db:
        all_tasks = db.query(ActionItem).filter(
            ActionItem.user_id == user_id,
            ActionItem.created_at >= week_ago,
        ).all()
        done = [t for t in all_tasks if t.status == "done"]
        overdue = [t for t in all_tasks if t.status == "active" and t.due_at and t.due_at < now]
        proposed = [t for t in all_tasks if t.status == "proposed"]

        pvi_scores = db.query(PVIDailyScore).filter(
            PVIDailyScore.user_id == user_id,
            PVIDailyScore.date >= week_ago.date(),
        ).order_by(PVIDailyScore.date).all()

        emails_processed = db.query(Message).filter(
            Message.user_id == user_id,
            Message.ingested_at >= week_ago,
        ).count()

    # PVI sparkline
    pvi_map = {p.date: p.score for p in pvi_scores}
    sparkline = ""
    for i in range(7):
        d = (now - timedelta(days=6 - i)).date()
        score = pvi_map.get(d)
        if score is None:
            sparkline += "·"
        elif score >= 80:
            sparkline += "█"
        elif score >= 60:
            sparkline += "▆"
        elif score >= 40:
            sparkline += "▄"
        else:
            sparkline += "▂"

    avg_pvi = sum(p.score for p in pvi_scores) / len(pvi_scores) if pvi_scores else 0
    completion_rate = len(done) / len(all_tasks) * 100 if all_tasks else 0

    lines = [
        f"# Weekly Review — {today.strftime('%d %b %Y')}",
        "",
        "## Performance Index",
        f"PVI trend (7d): {sparkline}  avg: {avg_pvi:.0f}",
        "",
        "## Tasks",
        f"✓ Completed: {len(done)}",
        f"⚠ Overdue: {len(overdue)}",
        f"○ Proposed (unreviewed): {len(proposed)}",
        f"Completion rate: {completion_rate:.0f}%",
        "",
        "## Inbox",
        f"Emails processed: {emails_processed}",
        "",
    ]

    if overdue:
        lines.append("## Still Outstanding")
        for t in overdue[:5]:
            due = t.due_at.strftime("%d %b") if t.due_at else "—"
            lines.append(f"• {t.title[:60]} (due {due})")
        lines.append("")

    return "\n".join(lines)
