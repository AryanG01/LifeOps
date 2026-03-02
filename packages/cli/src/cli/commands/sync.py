# packages/cli/src/cli/commands/sync.py
import typer
from rich import print as rprint
from rich.progress import Progress, SpinnerColumn, TextColumn


def cmd_sync():
    """Poll all sources (Gmail, Outlook, GCal), normalize events, and run LLM extraction."""
    from connectors.gmail.poller import poll_gmail
    from core.pipeline.normalizer import normalize_all_pending
    from core.llm.extractor import extract_all_pending
    from core.db.engine import get_db
    from core.db.models import Source
    from core.config import get_settings

    settings = get_settings()

    with Progress(SpinnerColumn(), TextColumn("{task.description}")) as p:
        task = p.add_task("Polling sources...")

        with get_db() as db:
            gmail_pairs = [(str(s.user_id), str(s.id)) for s in db.query(Source).filter_by(source_type="gmail").all()]
            outlook_pairs = [(str(s.user_id), str(s.id)) for s in db.query(Source).filter_by(source_type="outlook").all()]
            gcal_pairs = [(str(s.user_id), str(s.id)) for s in db.query(Source).filter_by(source_type="gcal").all()]

        for user_id, source_id in gmail_pairs:
            poll_gmail(user_id, source_id)

        if outlook_pairs:
            p.update(task, description="Polling Outlook...")
            from connectors.outlook.poller import poll_outlook
            for user_id, source_id in outlook_pairs:
                poll_outlook(user_id, source_id)

        if gcal_pairs:
            p.update(task, description="Polling Google Calendar...")
            from connectors.gcal.poller import poll_gcal
            for user_id, source_id in gcal_pairs:
                poll_gcal(user_id, source_id)

        p.update(task, description="Normalizing events...")
        normalized = normalize_all_pending()

        p.update(task, description="Running LLM extraction...")
        success, failed = extract_all_pending(settings.llm_prompt_version)

        p.update(task, description="Done!", completed=True)

    rprint(f"[green]✓ Normalized: {normalized} | Extracted: {success} | Failed: {failed}[/green]")
