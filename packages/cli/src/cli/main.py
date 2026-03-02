# packages/cli/src/cli/main.py
import typer
from cli.commands import init, connect, sync, inbox, tasks, digest, pvi, replay, telegram, llm
from cli.commands.today import cmd_today
from cli.commands import focus

app = typer.Typer(name="claw", help="Clawdbot Life Ops CLI", no_args_is_help=True)

app.add_typer(connect.app, name="connect", help="Connect external sources")
app.add_typer(inbox.app, name="inbox", help="View inbox messages")
app.add_typer(tasks.app, name="tasks", help="Manage action items")
app.add_typer(replay.app, name="replay", help="Replay pipeline stages")
app.add_typer(telegram.app, name="telegram", help="Telegram setup and delivery")
app.add_typer(llm.app, name="llm", help="LLM provider management (gemini / anthropic)")

app.command("init")(init.cmd_init)
app.command("sync")(sync.cmd_sync)
app.command("digest")(digest.cmd_digest)
app.command("pvi")(pvi.cmd_pvi)
app.command("snooze")(tasks.cmd_snooze)
app.command("today")(cmd_today)
app.add_typer(focus.app, name="focus", help="Focus/DND mode — silence Telegram reminders")

if __name__ == "__main__":
    app()
