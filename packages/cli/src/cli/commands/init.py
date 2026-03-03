# packages/cli/src/cli/commands/init.py
"""claw init — seed the DB with the user row from .env identity."""
import typer
from rich import print as rprint
from rich.panel import Panel


def cmd_init():
    """Seed the database with a User row for the current .env identity."""
    from core.config import get_settings
    from core.db.engine import get_db
    from core.db.models import User
    from pathlib import Path
    import uuid as _uuid

    settings = get_settings()

    # Fall back to a generated UUID if user_email not set
    lookup_email = settings.user_email or "local@clawdbot"

    with get_db() as db:
        existing = db.query(User).filter(User.email == lookup_email).first()
        if existing:
            rprint(Panel(
                f"User already exists\nID: {existing.id}\nName: {existing.display_name}",
                title="claw init"
            ))
            return

        user_id = str(settings.default_user_id) if settings.default_user_id else str(_uuid.uuid4())
        user = User(
            id=user_id,
            email=lookup_email,
            display_name=settings.user_display_name or "Clawdbot User",
            timezone=settings.user_timezone,
        )
        db.add(user)
        db.commit()

    # Write DEFAULT_USER_ID to .env if blank or missing
    env_path = Path(__file__).resolve().parents[6] / ".env"
    if env_path.exists():
        env_text = env_path.read_text()
        needs_update = (
            "DEFAULT_USER_ID=" not in env_text
            or "DEFAULT_USER_ID=\n" in env_text
            or "DEFAULT_USER_ID= \n" in env_text
        )
        if needs_update:
            with open(env_path, "a") as f:
                f.write(f"\nDEFAULT_USER_ID={user_id}\n")

    rprint(Panel(
        f"User created\nID: {user_id}\nName: {settings.user_display_name}\nEmail: {lookup_email}",
        title="claw init",
        style="green"
    ))
