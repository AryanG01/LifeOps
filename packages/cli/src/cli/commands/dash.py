"""claw dash — live Textual TUI dashboard."""
from datetime import datetime, timezone, timedelta


def cmd_dash():
    """Launch the live Clawdbot dashboard (press q to quit, r to refresh, s to sync)."""
    from textual.app import App, ComposeResult
    from textual.widgets import Header, Footer, DataTable, Static
    from textual.containers import Horizontal
    from core.db.engine import get_db
    from core.db.models import ActionItem, Reminder, PVIDailyScore
    from core.config import get_settings

    settings = get_settings()
    uid = settings.default_user_id

    class ClawdApp(App):
        CSS = """
        Screen { layout: grid; grid-size: 2; grid-gutter: 1; }
        #tasks    { height: 100%; border: solid cyan; }
        #reminders { height: 100%; border: solid yellow; }
        #status   { height: 4; border: solid green; dock: bottom; }
        """
        BINDINGS = [
            ("q", "quit", "Quit"),
            ("r", "refresh", "Refresh"),
            ("s", "sync", "Sync"),
        ]

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            with Horizontal():
                yield DataTable(id="tasks")
                yield DataTable(id="reminders")
            yield Static(id="status")
            yield Footer()

        def on_mount(self) -> None:
            tasks_table = self.query_one("#tasks", DataTable)
            tasks_table.add_columns("Task", "Due", "Status")
            rem_table = self.query_one("#reminders", DataTable)
            rem_table.add_columns("Task", "In", "Channel")
            self.refresh_data()
            self.set_interval(60, self.refresh_data)

        def refresh_data(self) -> None:
            now = datetime.now(tz=timezone.utc)

            tasks_table = self.query_one("#tasks", DataTable)
            tasks_table.clear()
            rem_table = self.query_one("#reminders", DataTable)
            rem_table.clear()
            status = self.query_one("#status", Static)

            with get_db() as db:
                tasks = db.query(ActionItem).filter(
                    ActionItem.user_id == uid,
                    ActionItem.status.in_(["proposed", "active"]),
                ).order_by(ActionItem.due_at).limit(20).all()

                for t in tasks:
                    due = t.due_at.strftime("%m-%d %H:%M") if t.due_at else "-"
                    overdue = t.due_at and t.due_at < now
                    tasks_table.add_row(t.title[:35], due, "OVERDUE" if overdue else t.status)

                reminders = db.query(Reminder).filter(
                    Reminder.user_id == uid,
                    Reminder.status == "pending",
                    Reminder.remind_at >= now,
                ).order_by(Reminder.remind_at).limit(15).all()

                for r in reminders:
                    delta = int((r.remind_at - now).total_seconds() / 60)
                    in_str = f"{delta}m" if delta < 60 else f"{delta // 60}h"
                    task = db.query(ActionItem).filter_by(id=r.action_item_id).first()
                    title = task.title[:30] if task else str(r.action_item_id)[:8]
                    rem_table.add_row(title, in_str, r.channel)

                pvi = db.query(PVIDailyScore).filter_by(
                    user_id=uid, date=now.date()
                ).first()
                pvi_str = f"PVI: {pvi.score} ({pvi.regime})" if pvi else "PVI: —"

            status.update(
                f"[bold]{pvi_str}[/bold]  |  Tasks: {len(tasks)}  |  "
                f"Reminders: {len(reminders)}  |  {now.strftime('%H:%M:%S')}"
            )

        def action_sync(self) -> None:
            import subprocess
            subprocess.Popen(["claw", "sync"])
            self.notify("Sync triggered in background", severity="information")

        def action_refresh(self) -> None:
            self.refresh_data()

    ClawdApp().run()
