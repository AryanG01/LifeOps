# packages/cli/src/cli/commands/telegram.py
"""
Telegram setup guide and test command.

BotFather setup:
  1. Open Telegram, search @BotFather
  2. Send /newbot, follow prompts → get your BOT_TOKEN
  3. Start a chat with your new bot
  4. Run: claw telegram chat-id → reveals your CHAT_ID
  5. Add to .env:
       TELEGRAM_BOT_TOKEN=<token>
       TELEGRAM_CHAT_ID=<chat_id>
       TELEGRAM_ENABLED=true
"""
import typer
from rich import print as rprint
from rich.panel import Panel
from rich.console import Console

app = typer.Typer()
console = Console()

BOTFATHER_GUIDE = """
[bold]Telegram Setup Guide[/bold]

1. Open Telegram → search [cyan]@BotFather[/cyan]
2. Send [yellow]/newbot[/yellow] and follow prompts
3. Copy your [green]BOT_TOKEN[/green]
4. Start a chat with your new bot (click Start)
5. Run [cyan]claw telegram chat-id --token <TOKEN>[/cyan] to get your CHAT_ID
6. Add to [yellow].env[/yellow]:
   [green]TELEGRAM_BOT_TOKEN=<token>[/green]
   [green]TELEGRAM_CHAT_ID=<chat_id>[/green]
   [green]TELEGRAM_ENABLED=true[/green]
7. Test with [cyan]claw telegram test[/cyan]
"""


@app.command("setup")
def cmd_setup():
    """Show BotFather setup guide."""
    console.print(Panel(BOTFATHER_GUIDE, title="Telegram Setup", border_style="cyan"))


@app.command("chat-id")
def cmd_chat_id(
    token: str = typer.Option(..., "--token", "-t", help="Bot token from BotFather"),
):
    """Fetch your Telegram chat ID (run after messaging the bot)."""
    import httpx

    rprint("Fetching updates from Telegram...")
    try:
        resp = httpx.get(
            f"https://api.telegram.org/bot{token}/getUpdates",
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        updates = data.get("result", [])
        if not updates:
            rprint("[yellow]No updates found. Send a message to your bot first, then retry.[/yellow]")
            return
        for update in updates:
            msg = update.get("message", {})
            chat = msg.get("chat", {})
            chat_id = chat.get("id")
            username = chat.get("username") or chat.get("first_name", "unknown")
            if chat_id:
                rprint(f"[green]Chat ID: {chat_id}[/green] (user: {username})")
                rprint(f"\nAdd to .env:\n  TELEGRAM_CHAT_ID={chat_id}")
                return
        rprint("[yellow]Could not extract chat ID from updates.[/yellow]")
    except Exception as exc:
        rprint(f"[red]Error: {exc}[/red]")


@app.command("test")
def cmd_test():
    """Send a test message using configured credentials."""
    from core.telegram_client import send_message
    rprint("Sending test message to Telegram...")
    ok = send_message("🤖 *Clawdbot* is connected and ready!")
    if ok:
        rprint("[green]✓ Message sent successfully[/green]")
    else:
        rprint("[red]✗ Failed — check TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_ENABLED in .env[/red]")
