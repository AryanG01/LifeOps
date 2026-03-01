# packages/cli/src/cli/commands/init.py
import typer
from rich import print as rprint
from core.db.engine import get_db
from core.db.models import User
from core.config import get_settings


def cmd_init():
    """Initialize the Clawdbot database and default user."""
    settings = get_settings()
    rprint("[bold]Clawdbot Life Ops — Init[/bold]")

    with get_db() as db:
        existing = db.query(User).filter_by(id=settings.default_user_id).first()
        if not existing:
            user = User(
                id=settings.default_user_id,
                email="local@clawdbot",
                display_name="Local User",
                timezone=settings.user_timezone,
            )
            db.add(user)
            db.commit()
            rprint("[green]✓ Created default user[/green]")
        else:
            rprint("[yellow]User already exists[/yellow]")

    rprint("[green]✓ Init complete. Run: claw connect gmail[/green]")
