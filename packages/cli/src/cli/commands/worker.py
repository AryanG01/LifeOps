# packages/cli/src/cli/commands/worker.py
"""
claw worker start  — launch the APScheduler background worker inline.
"""
import typer
from rich import print as rprint

app = typer.Typer()


@app.command("start")
def cmd_start():
    """Start the background scheduler (poll Gmail, extract, reminders, daily digest)."""
    from core.config import get_settings
    s = get_settings()

    rprint("[bold green]Starting Clawdbot worker...[/bold green]")
    rprint(f"  Gmail poll interval : [cyan]{s.gmail_poll_interval_minutes}m[/cyan]")
    rprint(f"  LLM extraction      : every [cyan]5m[/cyan]")
    rprint(f"  Reminders dispatch  : every [cyan]1m[/cyan]")
    rprint(f"  Daily digest        : [cyan]07:00 {s.user_timezone}[/cyan]")
    rprint("[dim]Press Ctrl+C to stop.[/dim]\n")

    try:
        import sys, os
        # Resolve project root (packages/cli/src/cli/commands/ → 5 levels up)
        _project_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), *[".."] * 5)
        )
        _worker_src = os.path.join(_project_root, "apps", "worker", "src")
        if _worker_src not in sys.path:
            sys.path.insert(0, _worker_src)
        from worker.main import start
        start()
    except ImportError as exc:
        rprint(f"[red]Worker package not importable: {exc}[/red]")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        rprint("\n[yellow]Worker stopped.[/yellow]")
