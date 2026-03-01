# packages/cli/src/cli/commands/connect.py
import typer
from rich import print as rprint
from pathlib import Path

app = typer.Typer()


@app.command("gmail")
def connect_gmail(
    credentials: str = typer.Option(
        "~/.config/clawdbot/gmail_credentials.json",
        "--credentials", "-c",
        help="Path to Google OAuth credentials JSON",
    )
):
    """Connect Gmail via OAuth."""
    from connectors.gmail.auth import run_oauth_flow
    from core.db.engine import get_db
    from core.db.models import Source
    from core.config import get_settings

    settings = get_settings()
    creds_path = str(Path(credentials).expanduser())

    if not Path(creds_path).exists():
        rprint(f"[red]Credentials file not found: {creds_path}[/red]")
        rprint("Download OAuth credentials from Google Cloud Console.")
        raise typer.Exit(1)

    rprint("Opening browser for Gmail OAuth...")
    run_oauth_flow(creds_path)
    rprint("[green]✓ Gmail connected[/green]")

    with get_db() as db:
        existing = db.query(Source).filter_by(
            user_id=settings.default_user_id, source_type="gmail"
        ).first()
        if not existing:
            db.add(Source(
                user_id=settings.default_user_id,
                source_type="gmail",
                display_name="Gmail",
                config_json={},
            ))
            db.commit()
            rprint("[green]✓ Gmail source registered[/green]")
        else:
            rprint("[yellow]Gmail source already registered[/yellow]")
