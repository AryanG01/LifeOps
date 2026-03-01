# packages/cli/src/cli/main.py
import typer
from cli.commands import init, connect, sync, inbox, tasks, digest, pvi, replay

app = typer.Typer(name="claw", help="Clawdbot Life Ops CLI", no_args_is_help=True)

app.add_typer(connect.app, name="connect", help="Connect external sources")
app.add_typer(inbox.app, name="inbox", help="View inbox messages")
app.add_typer(tasks.app, name="tasks", help="Manage action items")
app.add_typer(replay.app, name="replay", help="Replay pipeline stages")

app.command("init")(init.cmd_init)
app.command("sync")(sync.cmd_sync)
app.command("digest")(digest.cmd_digest)
app.command("pvi")(pvi.cmd_pvi)
app.command("snooze")(tasks.cmd_snooze)

if __name__ == "__main__":
    app()
