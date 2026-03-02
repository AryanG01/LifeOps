# packages/cli/src/cli/commands/tasks.py
import typer
from rich import print as rprint
from rich.table import Table
from rich.console import Console

app = typer.Typer()
console = Console()


@app.command("list")
def list_tasks(
    status: str = typer.Option(None, "--status", "-s",
                               help="Filter by status: proposed|active|done|dismissed"),
):
    """List action items."""
    from core.db.engine import get_db
    from core.db.models import ActionItem
    from core.config import get_settings

    settings = get_settings()

    table = Table(title="Tasks")
    table.add_column("ID (first 8)", style="dim")
    table.add_column("Title")
    table.add_column("Status")
    table.add_column("Due")
    table.add_column("Priority", justify="right")

    with get_db() as db:
        q = db.query(ActionItem).filter_by(user_id=settings.default_user_id)
        if status:
            q = q.filter(ActionItem.status == status)
        for t in q.order_by(ActionItem.due_at):
            due = t.due_at.strftime("%Y-%m-%d %H:%M") if t.due_at else "-"
            table.add_row(t.id[:8], t.title[:50], t.status, due, str(t.priority))

    console.print(table)


@app.command("accept")
def accept_task(task_id: str = typer.Argument(help="Task ID (full or prefix)")):
    """Accept a proposed task."""
    _change_status(task_id, "active")


@app.command("done")
def done_task(task_id: str = typer.Argument(help="Task ID")):
    """Mark a task as done."""
    _change_status(task_id, "done")


@app.command("dismiss")
def dismiss_task(task_id: str = typer.Argument(help="Task ID")):
    """Dismiss a proposed task."""
    _change_status(task_id, "dismissed")


def _change_status(task_id: str, new_status: str):
    from sqlalchemy import String
    from core.db.engine import get_db
    from core.db.models import ActionItem, Reminder
    from datetime import datetime, timezone

    with get_db() as db:
        task = db.query(ActionItem).filter(
            ActionItem.id.cast(String).like(f"{task_id}%")
        ).first()
        if not task:
            rprint(f"[red]Task not found: {task_id}[/red]")
            raise typer.Exit(1)
        task.status = new_status
        task.updated_at = datetime.now(tz=timezone.utc)
        if new_status in ("done", "dismissed"):
            db.query(Reminder).filter_by(
                action_item_id=task.id, status="pending"
            ).update({"status": "cancelled"})
        db.commit()
        rprint(f"[green]✓ Task {task.id[:8]} → {new_status}[/green]")


def cmd_snooze(
    task_id: str = typer.Argument(help="Task ID prefix"),
    hours: int = typer.Argument(1, help="Hours to snooze"),
):
    """Snooze the next pending reminder for a task."""
    from sqlalchemy import String
    from core.db.engine import get_db
    from core.db.models import Reminder
    from datetime import timedelta

    with get_db() as db:
        reminder = db.query(Reminder).filter(
            Reminder.action_item_id.cast(String).like(f"{task_id}%"),
            Reminder.status == "pending",
        ).order_by(Reminder.remind_at).first()
        if not reminder:
            rprint(f"[yellow]No pending reminders for {task_id}[/yellow]")
            raise typer.Exit(0)
        reminder.remind_at = reminder.remind_at + timedelta(hours=hours)
        reminder.status = "snoozed"
        db.commit()
        rprint(f"[green]✓ Snoozed until {reminder.remind_at.strftime('%Y-%m-%d %H:%M')}[/green]")
