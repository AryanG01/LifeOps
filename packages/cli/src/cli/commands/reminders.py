# packages/cli/src/cli/commands/reminders.py
"""
claw reminders list  — show upcoming pending reminders (joined with task title).
"""
import typer
from rich.table import Table
from rich.console import Console
from datetime import datetime, timezone

app = typer.Typer()
console = Console()


@app.command("list")
def list_reminders(
    limit: int = typer.Option(20, "--limit", "-n", help="Max reminders to show"),
):
    """List upcoming pending reminders with their task titles."""
    from core.db.engine import get_db
    from core.db.models import Reminder, ActionItem
    from core.config import get_settings

    settings = get_settings()
    now = datetime.now(tz=timezone.utc)

    table = Table(title="Upcoming Reminders")
    table.add_column("Task (first 8)", style="dim")
    table.add_column("Title", max_width=40)
    table.add_column("Remind At")
    table.add_column("In")
    table.add_column("Channel")
    table.add_column("Task Status")

    with get_db() as db:
        rows = (
            db.query(Reminder, ActionItem)
            .join(ActionItem, Reminder.action_item_id == ActionItem.id)
            .filter(
                Reminder.user_id == settings.default_user_id,
                Reminder.status == "pending",
                ActionItem.status.in_(["proposed", "active"]),
            )
            .order_by(Reminder.remind_at)
            .limit(limit)
            .all()
        )

        if not rows:
            console.print("[dim]No pending reminders.[/dim]")
            raise typer.Exit(0)

        for reminder, task in rows:
            remind_at = reminder.remind_at
            # Ensure tz-aware for arithmetic
            if remind_at.tzinfo is None:
                remind_at = remind_at.replace(tzinfo=timezone.utc)

            delta = remind_at - now
            total_minutes = int(delta.total_seconds() / 60)
            if total_minutes < 0:
                in_str = "[red]overdue[/red]"
            elif total_minutes < 60:
                in_str = f"{total_minutes}m"
            elif total_minutes < 1440:
                in_str = f"{total_minutes // 60}h {total_minutes % 60}m"
            else:
                in_str = f"{total_minutes // 1440}d"

            table.add_row(
                task.id[:8],
                task.title[:40],
                remind_at.strftime("%Y-%m-%d %H:%M"),
                in_str,
                reminder.channel,
                task.status,
            )

    console.print(table)
