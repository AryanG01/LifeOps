# packages/cli/src/cli/commands/replay.py
import typer
from rich import print as rprint

app = typer.Typer()


@app.command("extract")
def replay_extract(
    prompt_version: str = typer.Argument("v2", help="Prompt version to use for re-extraction"),
):
    """Re-run LLM extraction for all messages with a new prompt version."""
    from core.llm.extractor import extract_all_pending
    rprint(f"[bold]Replaying extraction with prompt version: {prompt_version}[/bold]")
    success, failed = extract_all_pending(prompt_version)
    rprint(f"[green]✓ Extracted: {success} | Failed: {failed}[/green]")
