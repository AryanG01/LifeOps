# packages/cli/src/cli/commands/pvi.py
import typer
from rich import print as rprint
from rich.panel import Panel
from rich.console import Console

console = Console()


def cmd_pvi(
    for_date: str = typer.Argument("today", help="Date (YYYY-MM-DD) or 'today'"),
):
    """Show today's Personal Volatility Index score and regime."""
    from core.pvi.engine import compute_pvi_daily
    from core.config import get_settings
    from datetime import datetime

    settings = get_settings()

    if for_date == "today":
        result = compute_pvi_daily(settings.default_user_id)
    else:
        result = compute_pvi_daily(
            settings.default_user_id,
            datetime.strptime(for_date, "%Y-%m-%d").date()
        )

    regime_colors = {
        "overloaded": "red",
        "peak": "yellow",
        "normal": "green",
        "recovery": "blue",
    }
    color = regime_colors.get(result["regime"], "white")

    content = (
        f"Score: [{color}]{result['score']}[/{color}]\n"
        f"Regime: [{color}]{result['regime']}[/{color}]\n"
        f"Drivers: {result['explanation']}\n\n"
        f"Policy:\n"
        f"  Max digest items: {result['policy']['max_digest_items']}\n"
        f"  Reminder cadence: {result['policy']['reminder_cadence']}\n"
        f"  Escalation: {result['policy']['escalation_level']}"
    )
    console.print(Panel(content, title=f"PVI — {for_date}", border_style=color))
