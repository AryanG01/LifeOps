#!/usr/bin/env python3
"""
Clawdbot Interactive Setup Wizard

Usage:
    python3 setup_wizard.py            # interactive — writes .env
    python3 setup_wizard.py --dry-run  # print what would be written, no file changes
"""
from __future__ import annotations

import sys
from pathlib import Path

# Check rich is available
try:
    from rich.prompt import Prompt, Confirm
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
except ImportError:
    print("ERROR: 'rich' is not installed. Run: pip install -e packages/core")
    sys.exit(1)

DRY_RUN = "--dry-run" in sys.argv
SCRIPT_DIR = Path(__file__).parent.resolve()
ENV_PATH = SCRIPT_DIR / ".env"
EXAMPLE_PATH = SCRIPT_DIR / ".env.example"

console = Console()


def _read_env() -> dict[str, str]:
    """Read existing .env into a dict (key -> value)."""
    if not ENV_PATH.exists():
        if EXAMPLE_PATH.exists():
            return _read_env_file(EXAMPLE_PATH)
        return {}
    return _read_env_file(ENV_PATH)


def _read_env_file(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            result[key.strip()] = val.strip()
    return result


def _write_env(values: dict[str, str]) -> None:
    """Merge wizard values into the existing .env file."""
    if not ENV_PATH.exists() and EXAMPLE_PATH.exists():
        import shutil
        shutil.copy(EXAMPLE_PATH, ENV_PATH)

    lines = ENV_PATH.read_text().splitlines() if ENV_PATH.exists() else []
    updated_keys: set[str] = set()
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, _, _ = stripped.partition("=")
            key = key.strip()
            if key in values:
                new_lines.append(f"{key}={values[key]}")
                updated_keys.add(key)
                continue
        new_lines.append(line)

    # Append any keys not already in the file
    for key, val in values.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={val}")

    ENV_PATH.write_text("\n".join(new_lines) + "\n")


def main() -> None:
    console.print(Panel(
        Text.assemble(
            ("Welcome to Clawdbot Setup Wizard\n", "bold cyan"),
            ("This wizard will fill in your .env credentials step by step.\n", ""),
            ("Press Enter to skip any optional step.", "dim"),
        ),
        title="Clawdbot",
        border_style="cyan",
    ))

    if DRY_RUN:
        console.print("[yellow]DRY RUN — no files will be changed.[/yellow]\n")

    existing = _read_env()
    collected: dict[str, str] = {}

    # -------------------------------------------------------------------------
    # Step 1 / 5: LLM Provider
    # -------------------------------------------------------------------------
    console.rule("[bold]Step 1 / 5: LLM Provider[/bold]")
    console.print(
        "Clawdbot uses Google Gemini by default (free: 250 req/day).\n"
        "Get a free key at: https://aistudio.google.com/app/apikey"
    )
    gemini_key = Prompt.ask(
        "  Gemini API key",
        default=existing.get("GEMINI_API_KEY", ""),
        password=True,
    )
    if gemini_key.strip():
        collected["GEMINI_API_KEY"] = gemini_key.strip()
        collected["LLM_PROVIDER"] = "gemini"

    use_anthropic = Confirm.ask(
        "  Also configure Anthropic Claude as fallback?", default=False
    )
    if use_anthropic:
        console.print("  Get a key at: https://console.anthropic.com/")
        anthropic_key = Prompt.ask(
            "  Anthropic API key",
            default=existing.get("ANTHROPIC_API_KEY", ""),
            password=True,
        )
        if anthropic_key.strip():
            collected["ANTHROPIC_API_KEY"] = anthropic_key.strip()

    # -------------------------------------------------------------------------
    # Step 2 / 5: Telegram
    # -------------------------------------------------------------------------
    console.rule("[bold]Step 2 / 5: Telegram[/bold]")
    console.print(
        "Clawdbot sends digests, reminders, and task alerts to your Telegram.\n"
        "\n"
        "  1. Open Telegram and message @BotFather\n"
        "  2. Send /newbot and follow the prompts\n"
        "  3. Copy the token (looks like: 8621657972:AAF62J_6tHlh...)\n"
    )
    bot_token = Prompt.ask(
        "  Telegram bot token",
        default=existing.get("TELEGRAM_BOT_TOKEN", ""),
        password=True,
    )
    if bot_token.strip():
        collected["TELEGRAM_BOT_TOKEN"] = bot_token.strip()
        console.print(
            "\n  To find your chat ID:\n"
            "  1. Start a chat with your new bot\n"
            "  2. Visit: https://api.telegram.org/bot<TOKEN>/getUpdates\n"
            "  3. Look for the 'id' field inside the 'chat' object\n"
        )
        chat_id = Prompt.ask(
            "  Your Telegram chat ID",
            default=existing.get("TELEGRAM_CHAT_ID", ""),
        )
        if chat_id.strip():
            collected["TELEGRAM_CHAT_ID"] = chat_id.strip()
            collected["TELEGRAM_ENABLED"] = "true"

    # -------------------------------------------------------------------------
    # Step 3 / 5: Gmail
    # -------------------------------------------------------------------------
    console.rule("[bold]Step 3 / 5: Gmail[/bold]")
    console.print(
        "Clawdbot reads your Gmail using OAuth (read-only by default).\n"
        "\n"
        "  1. Go to https://console.cloud.google.com/\n"
        "  2. Create a project -> Enable Gmail API + Google Calendar API\n"
        "  3. APIs & Services -> Credentials -> Create OAuth 2.0 Client ID (Desktop app)\n"
        "  4. Download the JSON -> save to ~/.config/clawdbot/gmail_credentials.json\n"
        "  5. After this wizard, run: claw connect gmail\n"
    )
    creds_path = Prompt.ask(
        "  Path to Gmail credentials JSON",
        default=existing.get("GMAIL_CREDENTIALS_PATH", "~/.config/clawdbot/gmail_credentials.json"),
    )
    if creds_path.strip():
        collected["GMAIL_CREDENTIALS_PATH"] = creds_path.strip()

    # -------------------------------------------------------------------------
    # Step 4 / 5: Outlook / NUS (optional)
    # -------------------------------------------------------------------------
    console.rule("[bold]Step 4 / 5: Outlook / NUS Exchange (optional)[/bold]")
    use_outlook = Confirm.ask(
        "  Configure Outlook/NUS Exchange?", default=False
    )
    if use_outlook:
        console.print(
            "\n  1. Go to https://portal.azure.com/ -> Azure Active Directory\n"
            "  2. App registrations -> New registration\n"
            "     Supported account types: 'Accounts in any organizational directory'\n"
            "  3. Add redirect URI: https://login.microsoftonline.com/common/oauth2/nativeclient\n"
            "  4. Copy the Application (client) ID\n"
        )
        outlook_client_id = Prompt.ask(
            "  Outlook Application (client) ID",
            default=existing.get("OUTLOOK_CLIENT_ID", ""),
        )
        if outlook_client_id.strip():
            collected["OUTLOOK_CLIENT_ID"] = outlook_client_id.strip()
        tenant = Prompt.ask(
            "  Tenant ('organizations' for NUS/work, 'common' for personal)",
            default=existing.get("OUTLOOK_TENANT", "organizations"),
        )
        collected["OUTLOOK_TENANT"] = tenant.strip() or "organizations"

    # -------------------------------------------------------------------------
    # Step 5 / 5: Preferences
    # -------------------------------------------------------------------------
    console.rule("[bold]Step 5 / 5: Preferences[/bold]")
    timezone = Prompt.ask(
        "  Your timezone (pytz string, e.g. Asia/Singapore, America/New_York)",
        default=existing.get("USER_TIMEZONE", "Asia/Singapore"),
    )
    if timezone.strip():
        collected["USER_TIMEZONE"] = timezone.strip()

    display_name = Prompt.ask(
        "  Your display name",
        default=existing.get("USER_DISPLAY_NAME", ""),
    )
    if display_name.strip():
        collected["USER_DISPLAY_NAME"] = display_name.strip()

    email = Prompt.ask(
        "  Your email address",
        default=existing.get("USER_EMAIL", ""),
    )
    if email.strip():
        collected["USER_EMAIL"] = email.strip()

    # -------------------------------------------------------------------------
    # Summary + write
    # -------------------------------------------------------------------------
    console.rule()
    console.print("\n[bold]Summary of values to write:[/bold]")
    for key, val in collected.items():
        display = val if "KEY" not in key and "TOKEN" not in key else val[:8] + "..." if val else "(empty)"
        console.print(f"  {key} = {display}")

    if not collected:
        console.print("[yellow]No values entered — nothing to write.[/yellow]")
        return

    if DRY_RUN:
        console.print("\n[yellow]DRY RUN — nothing written.[/yellow]")
        return

    confirm = Confirm.ask("\n  Write these values to .env?", default=True)
    if confirm:
        _write_env(collected)
        console.print(f"\n[green]Written to {ENV_PATH}[/green]")

        # Seed the database with the user row
        import subprocess
        console.print("\n[dim]Running claw init to seed database...[/dim]")
        subprocess.run([sys.executable, "-m", "cli.main", "init"], check=False)

        console.print(
            "\n[bold cyan]Next steps:[/bold cyan]\n"
            "  claw connect gmail       # authorize Gmail OAuth\n"
            "  claw connect gcal        # optional: Google Calendar\n"
            "  claw connect outlook     # optional: NUS/Outlook\n"
            "  claw worker start        # start background worker\n"
        )
    else:
        console.print("[dim]Cancelled — .env unchanged.[/dim]")


if __name__ == "__main__":
    main()
