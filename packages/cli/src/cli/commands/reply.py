"""claw reply — view and send LLM-drafted email replies."""
import typer
from rich.table import Table
from rich.console import Console
from rich import print as rprint

app = typer.Typer()
console = Console()


@app.command("list")
def list_replies():
    """List messages that have draft replies waiting."""
    from core.db.engine import get_db
    from core.db.models import ReplyDraft, Message

    with get_db() as db:
        drafts = (
            db.query(ReplyDraft, Message)
            .join(Message, ReplyDraft.message_id == Message.id)
            .filter(ReplyDraft.status == "proposed")
            .limit(20)
            .all()
        )

        if not drafts:
            rprint("[dim]No reply drafts.[/dim]")
            raise typer.Exit(0)

        t = Table(title="Reply Drafts")
        t.add_column("Msg ID", style="dim")
        t.add_column("From")
        t.add_column("Subject")
        t.add_column("Tone")
        for draft, msg in drafts:
            t.add_row(str(msg.id)[:8], msg.sender[:30], msg.title[:40], draft.tone)
        console.print(t)


@app.command("view")
def view_reply(msg_id: str = typer.Argument(help="Message ID prefix (first 8 chars)")):
    """View the draft reply for a message."""
    from core.db.engine import get_db
    from core.db.models import ReplyDraft, Message

    with get_db() as db:
        draft = (
            db.query(ReplyDraft)
            .join(Message, ReplyDraft.message_id == Message.id)
            .filter(
                Message.id.like(f"{msg_id}%"),
                ReplyDraft.status == "proposed",
            )
            .first()
        )

        if not draft:
            rprint(f"[red]No draft found for {msg_id}[/red]")
            raise typer.Exit(1)

        rprint(f"\n[bold]Tone:[/bold] {draft.tone}")
        rprint(f"\n[bold]Draft:[/bold]\n{draft.draft_text}\n")


@app.command("send")
def send_reply(
    msg_id: str = typer.Argument(help="Message ID prefix (first 8 chars)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
):
    """Send the draft reply via Gmail (requires gmail.send scope — re-run claw connect gmail)."""
    import base64
    import email.mime.text

    from core.db.engine import get_db
    from core.db.models import ReplyDraft, Message

    with get_db() as db:
        draft_row = (
            db.query(ReplyDraft)
            .join(Message, ReplyDraft.message_id == Message.id)
            .filter(
                Message.id.like(f"{msg_id}%"),
                ReplyDraft.status == "proposed",
            )
            .first()
        )
        msg = db.query(Message).filter(Message.id.like(f"{msg_id}%")).first()

        if not draft_row or not msg:
            rprint(f"[red]Draft not found for {msg_id}[/red]")
            raise typer.Exit(1)

        rprint(f"\n[bold]To:[/bold] {msg.sender}")
        rprint(f"[bold]Re:[/bold] {msg.title}")
        rprint(f"\n{draft_row.draft_text[:300]}...\n")

        if not yes:
            confirmed = typer.confirm("Send this reply?")
            if not confirmed:
                rprint("[yellow]Cancelled.[/yellow]")
                raise typer.Exit(0)

        try:
            from connectors.gmail.auth import get_credentials
            from googleapiclient.discovery import build

            creds = get_credentials()
            service = build("gmail", "v1", credentials=creds, cache_discovery=False)

            mime_msg = email.mime.text.MIMEText(draft_row.draft_text)
            mime_msg["To"] = msg.sender
            mime_msg["Subject"] = f"Re: {msg.title}"
            if msg.external_id:
                mime_msg["In-Reply-To"] = msg.external_id
                mime_msg["References"] = msg.external_id

            raw = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode()
            service.users().messages().send(
                userId="me",
                body={"raw": raw, "threadId": msg.external_id},
            ).execute()

            draft_row.status = "sent"
            db.commit()
            rprint("[green]✓ Reply sent.[/green]")

        except Exception as exc:
            rprint(f"[red]Send failed: {exc}[/red]")
            raise typer.Exit(1)
