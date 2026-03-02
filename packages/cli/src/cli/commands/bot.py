# packages/cli/src/cli/commands/bot.py
"""
claw bot start  — launch the interactive Telegram bot process.
"""
import typer
from rich import print as rprint

app = typer.Typer()


@app.command("start")
def cmd_start():
    """Start the interactive Telegram bot (long-polling)."""
    from core.config import get_settings
    s = get_settings()

    if not s.telegram_bot_token:
        rprint("[red]Error: TELEGRAM_BOT_TOKEN not set in .env[/red]")
        rprint("  1. Create a bot: message @BotFather on Telegram → /newbot")
        rprint("  2. Add TELEGRAM_BOT_TOKEN=<token> to your .env")
        raise typer.Exit(1)

    rprint("[bold green]Starting Clawdbot bot...[/bold green]")
    rprint(f"  Bot token    : [cyan]{s.telegram_bot_token[:10]}...[/cyan]")
    rprint(f"  Chat ID guard: [cyan]{s.telegram_chat_id}[/cyan]")
    rprint("[dim]Press Ctrl+C to stop.[/dim]\n")

    try:
        import sys, os
        _project_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), *[".."] * 5)
        )
        _bot_src = os.path.join(_project_root, "apps", "bot", "src")
        if _bot_src not in sys.path:
            sys.path.insert(0, _bot_src)
        from bot.main import run
        run()
    except ImportError as exc:
        rprint(f"[red]Bot package not importable: {exc}[/red]")
        rprint("  Install with: pip install -e apps/bot/")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        rprint("\n[yellow]Bot stopped.[/yellow]")
