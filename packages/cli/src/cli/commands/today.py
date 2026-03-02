"""claw today — morning briefing: tasks due today, next reminder, PVI, upcoming events."""
from datetime import datetime, timezone, timedelta
from rich.console import Console
from rich.table import Table
from rich import print as rprint

console = Console()


def cmd_today():
    """Quick morning briefing — due today, reminders, PVI, calendar."""
    from core.db.engine import get_db
    from core.db.models import ActionItem, Reminder, PVIDailyScore, CalendarEvent
    from core.config import get_settings

    settings = get_settings()
    now = datetime.now(tz=timezone.utc)
    today = now.date()
    tomorrow = today + timedelta(days=1)
    uid = settings.default_user_id

    with get_db() as db:
        # Tasks due today or overdue
        due_today = db.query(ActionItem).filter(
            ActionItem.user_id == uid,
            ActionItem.status.in_(["proposed", "active"]),
            ActionItem.due_at < datetime(tomorrow.year, tomorrow.month, tomorrow.day, tzinfo=timezone.utc),
        ).order_by(ActionItem.due_at).all()

        # Next 3 reminders
        next_reminders = db.query(Reminder).filter(
            Reminder.user_id == uid,
            Reminder.status == "pending",
            Reminder.remind_at >= now,
        ).order_by(Reminder.remind_at).limit(3).all()

        # Today's PVI
        pvi = db.query(PVIDailyScore).filter_by(user_id=uid, date=today).first()

        # Upcoming calendar events (next 24h)
        upcoming_events = db.query(CalendarEvent).filter(
            CalendarEvent.user_id == uid,
            CalendarEvent.start_at >= now,
            CalendarEvent.start_at < now + timedelta(hours=24),
        ).order_by(CalendarEvent.start_at).limit(5).all()

        rprint(f"\n[bold cyan]☀ Good morning — {today.strftime('%A, %d %B %Y')}[/bold cyan]\n")

        # PVI
        if pvi:
            regime_colour = {"calm": "green", "normal": "cyan", "surge": "yellow", "crisis": "red"}.get(pvi.regime, "white")
            rprint(f"[bold]PVI:[/bold] [{regime_colour}]{pvi.score} ({pvi.regime})[/{regime_colour}]  {pvi.explanation[:80]}\n")

        # Tasks due
        if due_today:
            t = Table(title="Due Today", box=None, padding=(0, 2))
            t.add_column("Task")
            t.add_column("Due", style="dim")
            t.add_column("Status")
            for task in due_today:
                due_str = task.due_at.strftime("%H:%M") if task.due_at else "no time"
                overdue = task.due_at and task.due_at < now
                status_str = "[red]OVERDUE[/red]" if overdue else task.status
                t.add_row(task.title[:50], due_str, status_str)
            console.print(t)
        else:
            rprint("[green]✓ Nothing due today[/green]")

        # Next reminders
        if next_reminders:
            rprint("\n[bold]Next reminders:[/bold]")
            for r in next_reminders:
                delta_min = int((r.remind_at - now).total_seconds() / 60)
                in_str = f"{delta_min}m" if delta_min < 60 else f"{delta_min // 60}h"
                rprint(f"  ⏰ in {in_str} — {r.channel}")

        # Calendar
        if upcoming_events:
            rprint("\n[bold]Upcoming (24h):[/bold]")
            for ev in upcoming_events:
                start = ev.start_at.strftime("%H:%M")
                rprint(f"  📅 {start} — {ev.title[:50]}")

        rprint("")
