# packages/cli/src/cli/commands/digest.py
import typer
from rich import print as rprint
from rich.markdown import Markdown
from rich.console import Console

console = Console()


def cmd_digest(
    for_date: str = typer.Argument("today", help="Date (YYYY-MM-DD) or 'today'"),
):
    """Generate and display today's digest."""
    from core.digest.generator import generate_digest
    from core.db.engine import get_db
    from core.db.models import Digest
    from core.config import get_settings
    from datetime import date as date_cls

    settings = get_settings()

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
