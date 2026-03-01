# packages/cli/src/cli/commands/inbox.py
import typer
from rich import print as rprint
from rich.table import Table
from rich.console import Console

app = typer.Typer()
console = Console()


@app.command("list")
def list_inbox(
    canvas_only: bool = typer.Option(False, "--canvas", help="Show Canvas emails only"),
    limit: int = typer.Option(20, "--limit", "-n"),
):
    """List recent inbox messages with summaries."""
    from core.db.engine import get_db
    from core.db.models import Message, MessageSummary
    from core.config import get_settings

    settings = get_settings()
    with get_db() as db:
        q = db.query(Message, MessageSummary).join(
            MessageSummary, MessageSummary.message_id == Message.id, isouter=True
        ).filter(Message.user_id == settings.default_user_id)
        if canvas_only:
            q = q.filter(Message.is_canvas == True)  # noqa: E712
        rows = q.order_by(Message.message_ts.desc()).limit(limit).all()

    table = Table(title="Inbox", show_lines=True)
    table.add_column("Date", style="dim")
    table.add_column("From")
    table.add_column("Subject")
    table.add_column("Summary")
    table.add_column("Canvas", justify="center")

    for msg, summary in rows:
        date_str = msg.message_ts.strftime("%m/%d %H:%M") if msg.message_ts else "-"
        short = (summary.summary_short[:60] if summary else msg.body_preview[:60]) or "-"
        canvas_mark = "✓" if msg.is_canvas else ""
        table.add_row(date_str, msg.sender[:30], msg.title[:40], short, canvas_mark)

    console.print(table)
