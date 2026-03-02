"""claw focus — DND mode: silence Telegram reminders for a set duration."""
import typer
from datetime import datetime, timezone, timedelta
from rich import print as rprint
from rich.console import Console

app = typer.Typer()
console = Console()


@app.command("start")
def focus_start(
    duration: str = typer.Argument("1h", help="Duration: 30m, 2h, 90m"),
):
    """Start a focus session (silences Telegram reminders)."""
    from core.db.engine import get_db
    from core.db.models import FocusSession
    from core.config import get_settings

    settings = get_settings()
    now = datetime.now(tz=timezone.utc)

    duration = duration.strip().lower()
    if duration.endswith("h"):
        minutes = int(duration[:-1]) * 60
    elif duration.endswith("m"):
        minutes = int(duration[:-1])
    else:
        rprint("[red]Invalid duration. Use format: 30m, 2h, 90m[/red]")
        raise typer.Exit(1)

    ends_at = now + timedelta(minutes=minutes)

    with get_db() as db:
        db.query(FocusSession).filter(
            FocusSession.user_id == settings.default_user_id,
            FocusSession.is_active == True,  # noqa: E712
        ).update({"is_active": False})
        db.add(FocusSession(
            user_id=settings.default_user_id,
            ends_at=ends_at,
            is_active=True,
        ))
        db.commit()

    rprint(f"[green]🎯 Focus mode ON until {ends_at.strftime('%H:%M')} UTC ({minutes}min)[/green]")
    rprint("[dim]Telegram reminders silenced. Run: claw focus end — to stop early.[/dim]")


@app.command("status")
def focus_status():
    """Show current focus session status."""
    from core.db.engine import get_db
    from core.db.models import FocusSession
    from core.config import get_settings

    settings = get_settings()
    now = datetime.now(tz=timezone.utc)

    with get_db() as db:
        session = db.query(FocusSession).filter(
            FocusSession.user_id == settings.default_user_id,
            FocusSession.is_active == True,  # noqa: E712
            FocusSession.ends_at > now,
        ).first()

        if not session:
            rprint("[dim]No active focus session.[/dim]")
        else:
            remaining = int((session.ends_at - now).total_seconds() / 60)
            rprint(f"[green]🎯 Focus mode active — {remaining}min remaining (ends {session.ends_at.strftime('%H:%M')} UTC)[/green]")


@app.command("end")
def focus_end():
    """End the current focus session early."""
    from core.db.engine import get_db
    from core.db.models import FocusSession
    from core.config import get_settings

    settings = get_settings()
    now = datetime.now(tz=timezone.utc)

    with get_db() as db:
        updated = db.query(FocusSession).filter(
            FocusSession.user_id == settings.default_user_id,
            FocusSession.is_active == True,  # noqa: E712
        ).update({"is_active": False, "ended_early_at": now})
        db.commit()

    if updated:
        rprint("[yellow]Focus mode ended.[/yellow]")
    else:
        rprint("[dim]No active focus session to end.[/dim]")
