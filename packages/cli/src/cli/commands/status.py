# packages/cli/src/cli/commands/status.py
"""claw status — show current user, connected sources, and worker heartbeat."""
from rich.table import Table
from rich.console import Console
from rich import print as rprint

console = Console()


def cmd_status():
    """Show current user, connected sources, and worker heartbeat."""
    from core.config import get_settings
    from core.db.engine import get_db
    from core.db.models import User, Source
    from datetime import datetime, timezone

    settings = get_settings()
    uid = settings.default_user_id

    with get_db() as db:
        user = db.query(User).filter(User.id == uid).first()
        sources = db.query(Source).filter(Source.user_id == uid).all()

        display_name = user.display_name if user else "(unknown)"
        email = user.email if user else "(unknown)"

        # Worker heartbeat: check most recent heartbeat row if table exists
        heartbeat_age = None
        try:
            from sqlalchemy import text
            row = db.execute(
                text("SELECT updated_at FROM worker_heartbeats ORDER BY updated_at DESC LIMIT 1")
            ).fetchone()
            if row:
                delta = datetime.now(timezone.utc) - row[0].replace(tzinfo=timezone.utc)
                heartbeat_age = f"{int(delta.total_seconds() // 60)}m ago"
        except Exception:
            heartbeat_age = "n/a"

    rprint(f"\n[bold]Clawdbot Status[/bold]")
    rprint(f"  User ID      : {uid}")
    rprint(f"  Display name : {display_name}")
    rprint(f"  Email        : {email}")
    rprint(f"  Telegram     : {'enabled' if settings.telegram_bot_token else 'disabled'}")
    rprint(f"  Worker       : {heartbeat_age or 'not running'}\n")

    tbl = Table(title="Connected Sources", show_header=True, header_style="bold cyan")
    tbl.add_column("Type")
    tbl.add_column("Display Name")
    tbl.add_column("Last Synced")
    for src in sources:
        synced = src.last_synced_at.strftime("%Y-%m-%d %H:%M") if src.last_synced_at else "never"
        tbl.add_row(src.source_type, src.display_name, synced)
    if not sources:
        tbl.add_row("—", "No sources connected", "—")
    console.print(tbl)
