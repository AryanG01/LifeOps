# packages/cli/src/cli/commands/digest.py
import typer
from rich import print as rprint
from rich.markdown import Markdown
from rich.console import Console

console = Console()


def cmd_digest(
    for_date: str = typer.Argument("today", help="Date (YYYY-MM-DD) or 'today'"),
    weekly: bool = typer.Option(False, "--weekly", "-w", help="Show 7-day review instead"),
):
    """Generate and display today's digest (or weekly review with --weekly)."""
    from core.config import get_settings

    settings = get_settings()

    if weekly:
        from core.digest.weekly import generate_weekly_review
        content = generate_weekly_review(settings.default_user_id)
        console.print(Markdown(content))
        return

    from core.digest.generator import generate_digest
    from core.db.engine import get_db
    from core.db.models import Digest

    if for_date == "today":
        content = generate_digest(settings.default_user_id)
    else:
        with get_db() as db:
            d = db.query(Digest).filter_by(
                user_id=settings.default_user_id, date=for_date
            ).first()
            if not d:
                rprint(f"[yellow]No digest found for {for_date}. Generating...[/yellow]")
                from datetime import datetime
                content = generate_digest(
                    settings.default_user_id,
                    datetime.strptime(for_date, "%Y-%m-%d").date()
                )
            else:
                content = d.content_md

    console.print(Markdown(content))

    if settings.telegram_enabled:
        from core.telegram_client import send_digest
        sent = send_digest(content)
        if sent:
            rprint("[dim]✓ Sent to Telegram[/dim]")
