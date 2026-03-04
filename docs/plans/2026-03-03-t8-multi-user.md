# T8: Multi-User Support — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Each user who clones the repo gets their own isolated credential set and Telegram chat.
**Architecture:** No DB schema changes needed (user_id already exists on every row). Changes are in config (per-user .env), setup.sh (creates user row), and Telegram guard (chat_id per-user).
**Tech Stack:** pydantic-settings, existing ORM, existing CLI
**Test command:** PYTHONPATH=packages/core/src:packages/connectors/src:packages/cli/src python3 -m pytest tests/unit/ -v

---

## Context

The DB schema already has `user_id` on every table (`users`, `sources`, `raw_events`, `messages`,
`action_items`, `reminders`, `pvi_daily_features`, `pvi_daily_scores`, `policies`, `digests`,
`calendar_events`, `focus_sessions`). The `User` model has `id`, `email`, `display_name`,
`timezone`, and `created_at`. Multi-user is therefore mostly a config and CLI bootstrapping
concern — no migrations required.

The `default_user_id` field in `Settings` (`config.py` line 41-43) already scopes every query.
Each deployer sets their own `.env` with their own `DEFAULT_USER_ID`, credentials, and
`TELEGRAM_CHAT_ID`. The Telegram bot already guards by `chat_id` so each user's bot instance
is isolated.

Existing API routes in `apps/api/src/api/main.py`:
- `GET /v1/sync`, `GET /v1/inbox`, `GET /v1/tasks`, `GET /v1/digest`, `GET /v1/pvi`,
  `GET /v1/replay`, `GET /health`

---

## Tasks

### Task 1 — Add `USER_DISPLAY_NAME` and `USER_EMAIL` to `config.py` Settings

**File:** `packages/core/src/core/config.py`

After the existing `default_user_id` field (currently line 41-43), add:

```python
user_display_name: str = Field(default="Clawdbot User")
user_email: str = Field(default="")
```

These map to `USER_DISPLAY_NAME` and `USER_EMAIL` in `.env`. They are used by `claw init` (Task 2)
to populate the `User` row without requiring interactive prompts.

Also add to `.env.example` (file: `.env.example`):

```dotenv
# Multi-user identity (used by `claw init` to seed the users table)
USER_DISPLAY_NAME=Your Name
USER_EMAIL=you@example.com
DEFAULT_USER_ID=          # Left blank — filled in automatically by `claw init`
```

**Verification:** `from core.config import get_settings; s = get_settings(); assert s.user_display_name`

---

### Task 2 — Update `claw init` command

**File:** `packages/cli/src/cli/commands/init.py`
(Create this file if it does not exist. If an `init.py` already exists, extend it.)

Logic:

1. Lazy-import `get_db`, `get_settings`, `User` inside the function body (avoids circular imports).
2. Load settings.
3. Check whether a `User` row already exists with `email == settings.user_email`.
   - If yes: print the existing `user_id` and exit (idempotent).
   - If no: create a new `User(email=settings.user_email, display_name=settings.user_display_name, timezone=settings.user_timezone)`.
4. After upsert, check whether `DEFAULT_USER_ID` is already set in `.env`.
   - If not set (empty string or missing): append `DEFAULT_USER_ID=<uuid>` to the project-root `.env` file.
   - Print a Rich panel: "User created: <display_name> (<user_id>)".

```python
# packages/cli/src/cli/commands/init.py
import typer
from rich import print as rprint
from rich.panel import Panel

app = typer.Typer()


@app.command()
def init():
    """Seed the database with a User row for the current .env identity."""
    from core.config import get_settings
    from core.db.engine import get_db
    from core.db.models import User
    from pathlib import Path
    import uuid as _uuid

    settings = get_settings()
    if not settings.user_email:
        rprint("[red]USER_EMAIL is not set in .env — cannot run init.[/red]")
        raise typer.Exit(1)

    with get_db() as db:
        existing = db.query(User).filter(User.email == settings.user_email).first()
        if existing:
            rprint(Panel(
                f"User already exists\nID: {existing.id}\nName: {existing.display_name}",
                title="claw init"
            ))
            return

        user = User(
            id=str(_uuid.uuid4()),
            email=settings.user_email,
            display_name=settings.user_display_name,
            timezone=settings.user_timezone,
        )
        db.add(user)
        db.commit()
        user_id = user.id

    # Write DEFAULT_USER_ID to .env if not already set
    env_path = Path(__file__).parent.parent.parent.parent.parent.parent.parent / ".env"
    env_text = env_path.read_text() if env_path.exists() else ""
    if "DEFAULT_USER_ID=" not in env_text or "DEFAULT_USER_ID=\n" in env_text:
        with open(env_path, "a") as f:
            f.write(f"\nDEFAULT_USER_ID={user_id}\n")

    rprint(Panel(
        f"User created\nID: {user_id}\nName: {settings.user_display_name}\nEmail: {settings.user_email}",
        title="claw init",
        style="green"
    ))
```

Register in `packages/cli/src/cli/main.py`:

```python
from cli.commands import init as init_cmd
app.add_typer(init_cmd.app, name="init")
```

---

### Task 3 — Write 2 unit tests for `claw init`

**File:** `tests/unit/test_init_command.py`

Use `unittest.mock` to patch `get_db` and `get_settings`. Do not touch the real DB.

Tests:

1. **`test_init_creates_user_row`** — mock DB returns no existing user; assert `db.add` and
   `db.commit` are called; assert the new `User` object has the correct email and display_name.
2. **`test_init_idempotent_existing_user`** — mock DB returns an existing user; assert `db.add`
   is NOT called; assert exit is clean (no exception).

```python
# tests/unit/test_init_command.py
from unittest.mock import MagicMock, patch


def _make_settings(**overrides):
    s = MagicMock()
    s.user_email = overrides.get("user_email", "test@example.com")
    s.user_display_name = overrides.get("user_display_name", "Test User")
    s.user_timezone = "Asia/Singapore"
    return s


def test_init_creates_user_row():
    mock_db = MagicMock()
    mock_db.__enter__ = lambda s: mock_db
    mock_db.__exit__ = MagicMock(return_value=False)
    mock_db.query.return_value.filter.return_value.first.return_value = None

    with patch("core.config.get_settings", return_value=_make_settings()), \
         patch("core.db.engine.get_db", return_value=mock_db), \
         patch("builtins.open", MagicMock()), \
         patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.read_text", return_value=""):
        from cli.commands.init import init
        init()

    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()
    added_user = mock_db.add.call_args[0][0]
    assert added_user.email == "test@example.com"
    assert added_user.display_name == "Test User"


def test_init_idempotent_existing_user():
    mock_existing = MagicMock()
    mock_existing.id = "existing-uuid"
    mock_existing.display_name = "Existing User"

    mock_db = MagicMock()
    mock_db.__enter__ = lambda s: mock_db
    mock_db.__exit__ = MagicMock(return_value=False)
    mock_db.query.return_value.filter.return_value.first.return_value = mock_existing

    with patch("core.config.get_settings", return_value=_make_settings()), \
         patch("core.db.engine.get_db", return_value=mock_db):
        from cli.commands.init import init
        init()

    mock_db.add.assert_not_called()
    mock_db.commit.assert_not_called()
```

Run: `PYTHONPATH=packages/core/src:packages/connectors/src:packages/cli/src python3 -m pytest tests/unit/test_init_command.py -v`

---

### Task 4 — Update `setup_wizard.py` and `.env.example`

**File:** `setup_wizard.py` (project root)

At the end of the wizard flow (after writing `.env`), add a call:

```python
import subprocess, sys
subprocess.run([sys.executable, "-m", "cli.main", "init"], check=False)
```

This seeds the DB immediately after first-time `.env` setup.

**File:** `.env.example`

Add a dedicated "Multi-user identity" section (see Task 1 snippet above). Also add a comment
block:

```dotenv
# --- Per-user setup ---
# Each person who clones this repo fills in their own credentials below.
# Run `claw init` once to create your User row and populate DEFAULT_USER_ID automatically.
```

No new tests needed for this task — it is a thin orchestration change verified by running
`python3 setup_wizard.py` in a dry-run environment.

---

### Task 5 — Add `claw status` command

**File:** `packages/cli/src/cli/commands/status.py`

Shows: `user_id`, `display_name`, `telegram_enabled`, connected sources (gmail/outlook/gcal with
`last_synced_at`), and worker heartbeat (most recent `updated_at` from a `worker_heartbeats` table
or equivalent).

```python
# packages/cli/src/cli/commands/status.py
import typer
from rich.table import Table
from rich.console import Console
from rich import print as rprint

app = typer.Typer()
console = Console()


@app.command()
def status():
    """Show current user, connected sources, and worker heartbeat."""
    from core.config import get_settings
    from core.db.engine import get_db
    from core.db.models import User, Source
    from datetime import datetime, timezone

    settings = get_settings()
    uid = settings.default_user_id

    with get_db() as db:
        user = db.query(User).filter(User.id == uid).first()
        sources = db.query(Source).filter(Source.user_id == uid).all()

        display_name = user.display_name if user else "(unknown)"
        email = user.email if user else "(unknown)"

        # Worker heartbeat: check most recent heartbeat row if table exists
        heartbeat_age = None
        try:
            from sqlalchemy import text
            row = db.execute(
                text("SELECT updated_at FROM worker_heartbeats ORDER BY updated_at DESC LIMIT 1")
            ).fetchone()
            if row:
                delta = datetime.now(timezone.utc) - row[0].replace(tzinfo=timezone.utc)
                heartbeat_age = f"{int(delta.total_seconds() // 60)}m ago"
        except Exception:
            heartbeat_age = "n/a"

    rprint(f"\n[bold]Clawdbot Status[/bold]")
    rprint(f"  User ID      : {uid}")
    rprint(f"  Display name : {display_name}")
    rprint(f"  Email        : {email}")
    rprint(f"  Telegram     : {'enabled' if settings.telegram_bot_token else 'disabled'}")
    rprint(f"  Worker       : {heartbeat_age or 'not running'}\n")

    tbl = Table(title="Connected Sources", show_header=True, header_style="bold cyan")
    tbl.add_column("Type")
    tbl.add_column("Display Name")
    tbl.add_column("Last Synced")
    for src in sources:
        synced = src.last_synced_at.strftime("%Y-%m-%d %H:%M") if src.last_synced_at else "never"
        tbl.add_row(src.source_type, src.display_name, synced)
    if not sources:
        tbl.add_row("—", "No sources connected", "—")
    console.print(tbl)
```

Register in `packages/cli/src/cli/main.py`:

```python
from cli.commands import status as status_cmd
app.add_typer(status_cmd.app, name="status")
```

---

### Task 6 — Write 3 unit tests for `claw status`

**File:** `tests/unit/test_status_command.py`

Tests:

1. **`test_status_shows_user_info`** — mock DB returns a `User` with known display_name/email;
   assert output contains those values (capture Rich output).
2. **`test_status_shows_sources`** — mock DB returns two `Source` rows; assert both source_type
   values appear in the printed table.
3. **`test_status_no_sources`** — mock DB returns empty source list; assert "No sources
   connected" appears in output.

```python
# tests/unit/test_status_command.py
from unittest.mock import MagicMock, patch
from io import StringIO


def _mock_source(source_type, display_name, last_synced_at=None):
    s = MagicMock()
    s.source_type = source_type
    s.display_name = display_name
    s.last_synced_at = last_synced_at
    return s


def _mock_user(display_name="Alice", email="alice@example.com"):
    u = MagicMock()
    u.display_name = display_name
    u.email = email
    return u


def _make_settings(uid="00000000-0000-0000-0000-000000000001"):
    s = MagicMock()
    s.default_user_id = uid
    s.telegram_bot_token = "tok"
    return s


def _make_mock_db(user, sources):
    mock_db = MagicMock()
    mock_db.__enter__ = lambda s: mock_db
    mock_db.__exit__ = MagicMock(return_value=False)

    def query_side_effect(model):
        from core.db.models import User, Source
        q = MagicMock()
        if model is User:
            q.filter.return_value.first.return_value = user
        elif model is Source:
            q.filter.return_value.all.return_value = sources
        return q

    mock_db.query.side_effect = query_side_effect
    mock_db.execute.return_value.fetchone.return_value = None
    return mock_db


def test_status_shows_user_info(capsys):
    mock_db = _make_mock_db(_mock_user("Alice", "alice@example.com"), [])
    with patch("core.config.get_settings", return_value=_make_settings()), \
         patch("core.db.engine.get_db", return_value=mock_db):
        from cli.commands.status import status
        status()
    out = capsys.readouterr().out
    assert "Alice" in out
    assert "alice@example.com" in out


def test_status_shows_sources(capsys):
    sources = [
        _mock_source("gmail", "Gmail"),
        _mock_source("outlook", "Outlook"),
    ]
    mock_db = _make_mock_db(_mock_user(), sources)
    with patch("core.config.get_settings", return_value=_make_settings()), \
         patch("core.db.engine.get_db", return_value=mock_db):
        from cli.commands.status import status
        status()
    out = capsys.readouterr().out
    assert "gmail" in out
    assert "outlook" in out


def test_status_no_sources(capsys):
    mock_db = _make_mock_db(_mock_user(), [])
    with patch("core.config.get_settings", return_value=_make_settings()), \
         patch("core.db.engine.get_db", return_value=mock_db):
        from cli.commands.status import status
        status()
    out = capsys.readouterr().out
    assert "No sources connected" in out
```

Run: `PYTHONPATH=packages/core/src:packages/connectors/src:packages/cli/src python3 -m pytest tests/unit/test_status_command.py -v`

---

## Acceptance Checklist

- [ ] Task 1: `user_display_name` and `user_email` fields exist in `Settings`
- [ ] Task 2: `claw init` creates User row and writes `DEFAULT_USER_ID` to `.env`
- [ ] Task 3: 2 init tests pass
- [ ] Task 4: `setup_wizard.py` calls `claw init`; `.env.example` has per-user section
- [ ] Task 5: `claw status` prints user info, sources table, and worker heartbeat
- [ ] Task 6: 3 status tests pass
- [ ] All 107 unit tests pass (102 existing + 5 new)

## Files Modified / Created

| Action | Path |
|--------|------|
| Modified | `packages/core/src/core/config.py` |
| Created  | `packages/cli/src/cli/commands/init.py` |
| Modified | `packages/cli/src/cli/main.py` |
| Created  | `packages/cli/src/cli/commands/status.py` |
| Modified | `setup_wizard.py` |
| Modified | `.env.example` |
| Created  | `tests/unit/test_init_command.py` |
| Created  | `tests/unit/test_status_command.py` |
