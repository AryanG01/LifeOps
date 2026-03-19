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
    ),
    label: str = typer.Option(
        "default",
        "--label", "-l",
        help="Account label, e.g. 'personal' or 'work'. Use a different label per Gmail account.",
    ),
    list_accounts: bool = typer.Option(
        False, "--list", help="List connected Gmail accounts without re-authenticating."
    ),
):
    """Connect Gmail via OAuth. Use --label to connect multiple accounts."""
    from core.db.engine import get_db
    from core.db.models import Source
    from core.config import get_settings

    settings = get_settings()

    if list_accounts:
        with get_db() as db:
            sources = db.query(Source).filter_by(
                user_id=settings.default_user_id, source_type="gmail"
            ).all()
            source_data = [
                (s.display_name, (s.config_json or {}).get("account_label", "default"),
                 (s.config_json or {}).get("email", "unknown"))
                for s in sources
            ]
        if not source_data:
            rprint("[yellow]No Gmail accounts connected.[/yellow]")
        for display_name, acct_label, email in source_data:
            rprint(f"  [{acct_label}] {email} — {display_name}")
        return

    from connectors.gmail.auth import run_oauth_flow, get_email_address

    creds_path = str(Path(credentials).expanduser())
    if not Path(creds_path).exists():
        rprint(f"[red]Credentials file not found: {creds_path}[/red]")
        rprint("Download OAuth credentials from Google Cloud Console.")
        raise typer.Exit(1)

    rprint(f"[bold]Starting Gmail OAuth (label: {label})...[/bold]")
    rprint("[yellow]First, open a NEW terminal on your local machine and run:[/yellow]")
    rprint(f"[cyan]  ssh -L 8080:localhost:8080 {__import__('os').environ.get('USER', 'user')}@<VM-IP>[/cyan]")
    rprint("[dim]Then a URL will appear below — copy it into your local browser.[/dim]\n")
    creds = run_oauth_flow(creds_path, account_label=label)

    # Discover the authenticated email address
    try:
        email_address = get_email_address(creds)
    except Exception:
        email_address = "unknown"

    display_name = "Gmail" if label == "default" else f"Gmail ({label})"

    with get_db() as db:
        # Warn if same email already registered under a different label
        existing_sources = db.query(Source).filter_by(
            user_id=settings.default_user_id, source_type="gmail"
        ).all()
        for src in existing_sources:
            src_email = (src.config_json or {}).get("email")
            src_label = (src.config_json or {}).get("account_label", "default")
            if src_email == email_address and src_label != label:
                rprint(f"[yellow]Warning: {email_address} is already connected under label '{src_label}'.[/yellow]")

        # Upsert: match by label (display_name) so re-running the same label updates, doesn't duplicate
        existing = db.query(Source).filter_by(
            user_id=settings.default_user_id, source_type="gmail", display_name=display_name
        ).first()
        if not existing:
            db.add(Source(
                user_id=settings.default_user_id,
                source_type="gmail",
                display_name=display_name,
                config_json={"account_label": label, "email": email_address},
            ))
            db.commit()
            rprint(f"[green]✓ {display_name} connected ({email_address})[/green]")
        else:
            existing.config_json = {"account_label": label, "email": email_address}
            db.commit()
            rprint(f"[green]✓ {display_name} token refreshed ({email_address})[/green]")


@app.command("outlook")
def connect_outlook():
    """Authenticate with Microsoft Graph (Outlook + NUS email)."""
    from connectors.outlook.auth import run_oauth_flow
    from core.db.engine import get_db
    from core.db.models import Source
    from core.config import get_settings

    settings = get_settings()
    rprint("[bold]Connecting Outlook via Microsoft Graph...[/bold]")
    rprint("[dim]You will be prompted to open a URL and enter a short code.[/dim]\n")

    try:
        run_oauth_flow()
    except Exception as e:
        rprint(f"[red]Auth failed: {e}[/red]")
        raise typer.Exit(1)

    with get_db() as db:
        existing = db.query(Source).filter_by(
            user_id=settings.default_user_id, source_type="outlook"
        ).first()
        if not existing:
            db.add(Source(
                user_id=settings.default_user_id,
                source_type="outlook",
                display_name="Outlook/NUS",
                config_json={},
            ))
            db.commit()
            rprint("[green]✓ Outlook connected and registered.[/green]")
        else:
            rprint("[green]✓ Outlook token refreshed.[/green]")


@app.command("gcal")
def connect_gcal():
    """Connect Google Calendar (re-authenticates Gmail OAuth with calendar.readonly scope)."""
    from connectors.gmail.auth import run_oauth_flow
    from core.db.engine import get_db
    from core.db.models import Source
    from core.config import get_settings

    settings = get_settings()
    rprint("[bold]Connecting Google Calendar...[/bold]")
    rprint("[dim]Re-authenticating Gmail OAuth to add calendar.readonly scope.[/dim]\n")

    credentials = "~/.config/clawdbot/gmail_credentials.json"
    creds_path = str(Path(credentials).expanduser())
    if not Path(creds_path).exists():
        rprint(f"[red]Credentials file not found: {creds_path}[/red]")
        raise typer.Exit(1)

    try:
        run_oauth_flow(creds_path)
    except Exception as e:
        rprint(f"[red]Auth failed: {e}[/red]")
        raise typer.Exit(1)

    with get_db() as db:
        existing = db.query(Source).filter_by(
            user_id=settings.default_user_id, source_type="gcal"
        ).first()
        if not existing:
            db.add(Source(
                user_id=settings.default_user_id,
                source_type="gcal",
                display_name="Google Calendar",
                config_json={},
            ))
            db.commit()
    rprint("[green]✓ Google Calendar connected.[/green]")
    rprint("[dim]Run: claw sync — to pull in upcoming events.[/dim]")
