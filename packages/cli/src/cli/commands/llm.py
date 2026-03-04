# packages/cli/src/cli/commands/llm.py
"""
LLM provider management: switch between Gemini (free) and Anthropic.

Usage:
  claw llm status          — show current provider, model, key presence
  claw llm use gemini      — switch to Gemini (writes LLM_PROVIDER to .env)
  claw llm use anthropic   — switch to Anthropic
  claw llm test            — send a quick test prompt to verify the active provider
"""
import typer
from pathlib import Path
from rich import print as rprint
from rich.table import Table
from rich.console import Console

app = typer.Typer()
console = Console()

PROVIDERS = {"gemini", "anthropic"}
DOTENV_PATH = Path(__file__).resolve().parents[5] / ".env"


# ---------------------------------------------------------------------------
# .env helpers
# ---------------------------------------------------------------------------

def _read_dotenv() -> dict[str, str]:
    if not DOTENV_PATH.exists():
        return {}
    lines = DOTENV_PATH.read_text().splitlines()
    result: dict[str, str] = {}
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result


def _write_dotenv_key(key: str, value: str) -> None:
    """Update or add a single key in .env, preserving all other content."""
    if not DOTENV_PATH.exists():
        DOTENV_PATH.write_text(f"{key}={value}\n")
        return

    lines = DOTENV_PATH.read_text().splitlines()
    found = False
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{key}=") or stripped == key:
            new_lines.append(f"{key}={value}")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key}={value}")
    DOTENV_PATH.write_text("\n".join(new_lines) + "\n")


def _mask(value: str) -> str:
    if not value:
        return "[red]not set[/red]"
    if len(value) <= 8:
        return "[green]set[/green]"
    return f"[green]{value[:6]}...{value[-4:]}[/green]"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@app.command("status")
def cmd_status():
    """Show active LLM provider, model, and API key status."""
    from core.config import get_settings
    s = get_settings()

    table = Table(title="LLM Provider Status", show_header=True)
    table.add_column("Setting")
    table.add_column("Value")

    active = s.llm_provider
    table.add_row("Active provider", f"[bold cyan]{active}[/bold cyan]")
    table.add_row("LLM mode", s.llm_mode)

    table.add_section()
    table.add_row("[cyan]Gemini[/cyan]", "")
    table.add_row("  Model", s.gemini_model)
    table.add_row("  API key", _mask(s.gemini_api_key))

    table.add_section()
    table.add_row("[yellow]Anthropic[/yellow]", "")
    table.add_row("  Model", s.anthropic_model)
    table.add_row("  API key", _mask(s.anthropic_api_key))

    console.print(table)

    if active == "gemini" and not s.gemini_api_key:
        rprint("\n[red]⚠ GEMINI_API_KEY not set. Get it free at https://aistudio.google.com/app/apikey[/red]")
    elif active == "anthropic" and not s.anthropic_api_key:
        rprint("\n[red]⚠ ANTHROPIC_API_KEY not set.[/red]")


@app.command("use")
def cmd_use(
    provider: str = typer.Argument(help="Provider to activate: gemini or anthropic"),
):
    """Switch the active LLM provider (updates .env)."""
    provider = provider.lower()
    if provider not in PROVIDERS:
        rprint(f"[red]Unknown provider '{provider}'. Choose: gemini or anthropic[/red]")
        raise typer.Exit(1)

    _write_dotenv_key("LLM_PROVIDER", provider)

    # Invalidate the settings singleton so the next call re-reads .env
    import core.config as cfg
    cfg._settings = None

    from core.config import get_settings
    s = get_settings()

    if provider == "gemini":
        model = s.gemini_model
        key_ok = bool(s.gemini_api_key)
        tip = "Get free key: https://aistudio.google.com/app/apikey → set GEMINI_API_KEY in .env"
    else:
        model = s.anthropic_model
        key_ok = bool(s.anthropic_api_key)
        tip = "Set ANTHROPIC_API_KEY in .env"

    rprint(f"[green]✓ Switched to [bold]{provider}[/bold] ({model})[/green]")
    if not key_ok:
        rprint(f"[yellow]⚠ API key missing. {tip}[/yellow]")
    else:
        rprint("[dim]Run: claw llm test — to verify[/dim]")


@app.command("test")
def cmd_test(
    text: str = typer.Option(
        "Reminder: CS3230 assignment due tomorrow at 11:59pm. Submit on Canvas.",
        "--text", "-t",
        help="Text to extract from (defaults to a sample Canvas email)",
    ),
):
    """Send a test extraction to verify the active LLM provider works."""
    from core.config import get_settings
    from core.llm.extractor import _call_llm
    from core.llm.prompts.v1 import SYSTEM_PROMPT, USER_TEMPLATE
    import json
    import time

    s = get_settings()
    provider = s.llm_provider
    model = s.gemini_model if provider == "gemini" else s.anthropic_model

    rprint(f"[bold]Testing {provider} ({model})...[/bold]")

    user_prompt = USER_TEMPLATE.format(
        timezone=s.user_timezone,
        source_type="gmail",
        sender="notifications@instructure.com",
        title="Assignment due: CS3230 Problem Set 4",
        message_ts="2026-03-02T10:00:00+08:00",
        body=text,
    )

    t0 = time.monotonic()
    try:
        raw, in_tok, out_tok = _call_llm(SYSTEM_PROMPT, user_prompt)
        elapsed = time.monotonic() - t0

        # Try to parse the response
        try:
            parsed = json.loads(raw)
            rprint(f"[green]✓ Response received in {elapsed:.1f}s[/green]")
            rprint(f"[dim]Tokens: {in_tok} in / {out_tok} out[/dim]")
            items = parsed.get("action_items", [])
            rprint(f"[cyan]Action items extracted: {len(items)}[/cyan]")
            for item in items:
                rprint(f"  • {item.get('title', '?')} (priority {item.get('priority', '?')})")
        except json.JSONDecodeError:
            rprint(f"[yellow]⚠ Response not valid JSON (raw):[/yellow]\n{raw[:300]}")
    except Exception as exc:
        rprint(f"[red]✗ Error: {exc}[/red]")
        raise typer.Exit(1)
