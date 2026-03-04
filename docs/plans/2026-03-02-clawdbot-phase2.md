# Clawdbot Phase 2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade Clawdbot from a working MVP to a polished daily-driver — faster ingestion, lower LLM costs, richer UX, and two new source integrations (Outlook/NUS via Microsoft Graph + Google Calendar).

**Architecture:** Three pillars — (1) Latency/cost: Gmail History API delta polling + two-stage LLM triage gate. (2) UX: Textual TUI dashboard, `claw today` morning briefing, Focus/DND mode. (3) Integrations: Microsoft Graph connector (replaces/supplements Gmail, covers Outlook + NUS Exchange), Google Calendar connector with meeting prep summaries.

**Tech Stack:** Python 3.11, `msal` (Microsoft Graph auth), `textual` (TUI), `google-auth-oauthlib` (already installed for GCal), SQLAlchemy 2.x, Alembic, Typer+Rich, Gemini 2.5 Flash + 2.5 Flash-Lite (triage).

---

## PROGRESS TRACKER

- [x] Task 1: DB migration — calendar_events + focus_sessions tables
- [x] Task 2: Gmail History API delta polling (2-min latency)
- [x] Task 3: Two-stage LLM triage (cheap pre-filter)
- [x] Task 4: `claw today` morning briefing command
- [x] Task 5: Focus/DND mode (`claw focus start/status/end`)
- [x] Task 6: Microsoft Graph connector — auth (MSAL device code)
- [x] Task 7: Microsoft Graph connector — Outlook mail poller
- [x] Task 8: `claw connect outlook` + worker job
- [x] Task 9: Google Calendar connector — auth + event poller
- [x] Task 10: `claw connect gcal` + meeting prep summaries
- [x] Task 11: Textual TUI dashboard (`claw dash`)
- [x] Task 12: Weekly review digest (`claw digest --weekly`)
- [x] Task 13: Reply drafting (`claw reply list/view/send`)
- [x] Task 14: Unit tests for all Phase 2 components  ← DONE (86 tests passing)
- [x] Task 15: Update worker scheduler with new jobs  ← DONE

---

## Context for Implementor

### Project Layout
```
packages/
  core/src/core/
    config.py           — Settings singleton (get_settings)
    db/engine.py        — get_db() context manager
    db/models.py        — ORM models (add new ones here)
    llm/extractor.py    — extract_message(), extract_all_pending()
    pipeline/reminders.py — dispatch_due_reminders()
    tokens.py           — store_token()/get_token() (keyring + file fallback)
  connectors/src/connectors/
    gmail/auth.py       — get_credentials() → google.oauth2.Credentials
    gmail/poller.py     — poll_gmail(user_id, source_id)
    canvas/parser.py    — is_canvas_email(), parse_canvas_email()
  cli/src/cli/
    main.py             — Typer root; register new commands here
    commands/           — one file per command group
apps/
  worker/src/worker/
    main.py             — BlockingScheduler; add new jobs here
    jobs.py             — job_* functions called by scheduler
infra/
  alembic/versions/     — migrations; filename format: 000N_description.py
  alembic.ini           — run migrations from infra/ dir: cd infra && python3 -m alembic upgrade head
tests/unit/             — pytest; mock DB with MagicMock, no real DB needed
```

### Key Patterns
- **DB access:** Always `with get_db() as db:` — iterating ORM objects MUST happen inside the `with` block (DetachedInstanceError otherwise)
- **Settings:** `get_settings()` singleton reads `.env` from cwd — always run claw commands from project root
- **Lazy imports:** All heavy imports (`core.*`, `connectors.*`) inside command functions, not at module level
- **Token storage:** `store_token(service, username, dict)` / `get_token(service, username)` — uses macOS keychain
- **Logging:** `log = structlog.get_logger()` → `log.info("event_name", key=val)`
- **LLM models:** triage=`gemini-2.5-flash-lite`, extraction=`gemini-2.5-flash` (or `anthropic` if switched)
- **UUID storage:** All IDs stored as `str` (not UUID objects) — `Column(UUID(as_uuid=False))`
- **Run tests:** `python3 -m pytest tests/unit/ -v` from project root

---

## Task 1: DB Migration — calendar_events + focus_sessions

**Why first:** New tables needed by Tasks 9 and 5 respectively. All other tasks can proceed without migrations.

**Files:**
- Create: `infra/alembic/versions/0002_phase2_tables.py`
- Modify: `packages/core/src/core/db/models.py`

**Step 1: Create migration file**

```python
# infra/alembic/versions/0002_phase2_tables.py
"""phase2 tables: calendar_events, focus_sessions

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-02
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS calendar_events (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        source_id UUID REFERENCES sources(id) ON DELETE SET NULL,
        external_id TEXT NOT NULL,
        title TEXT NOT NULL,
        start_at TIMESTAMPTZ NOT NULL,
        end_at TIMESTAMPTZ NOT NULL,
        location TEXT,
        attendees_json JSONB NOT NULL DEFAULT '[]',
        description TEXT,
        is_all_day BOOLEAN NOT NULL DEFAULT FALSE,
        ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(user_id, external_id)
    );

    CREATE TABLE IF NOT EXISTS focus_sessions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        ends_at TIMESTAMPTZ NOT NULL,
        ended_early_at TIMESTAMPTZ,
        is_active BOOLEAN NOT NULL DEFAULT TRUE
    );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS focus_sessions;")
    op.execute("DROP TABLE IF EXISTS calendar_events;")
```

**Step 2: Add ORM models**

Append to `packages/core/src/core/db/models.py`:

```python
class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    source_id = Column(UUID(as_uuid=False), ForeignKey("sources.id", ondelete="SET NULL"))
    external_id = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    start_at = Column(DateTime(timezone=True), nullable=False)
    end_at = Column(DateTime(timezone=True), nullable=False)
    location = Column(Text)
    attendees_json = Column(JSON, nullable=False, default=list)
    description = Column(Text)
    is_all_day = Column(Boolean, nullable=False, default=False)
    ingested_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("user_id", "external_id"),)


class FocusSession(Base):
    __tablename__ = "focus_sessions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    ends_at = Column(DateTime(timezone=True), nullable=False)
    ended_early_at = Column(DateTime(timezone=True))
    is_active = Column(Boolean, nullable=False, default=True)
```

**Step 3: Run migration**

```bash
cd infra && python3 -m alembic upgrade head
```
Expected: `Running upgrade 0001 -> 0002`

**Step 4: Verify**

```bash
python3 -c "
from core.db.engine import get_db
from core.db.models import CalendarEvent, FocusSession
with get_db() as db:
    print('calendar_events:', db.query(CalendarEvent).count())
    print('focus_sessions:', db.query(FocusSession).count())
"
```

**Step 5: Commit**
```bash
git add infra/alembic/versions/0002_phase2_tables.py packages/core/src/core/db/models.py
git commit -m "feat: add calendar_events and focus_sessions tables (phase 2 migration)"
```

---

## Task 2: Gmail History API Delta Polling

**Why:** Reduces poll latency from 15 min → 2 min with trivially small API calls (only fetches what changed since last sync using Gmail's `historyId` cursor).

**Files:**
- Modify: `packages/connectors/src/connectors/gmail/poller.py`
- Modify: `packages/core/src/core/config.py` (change default interval)

**Background:** Gmail's `users.history.list` API returns only changes (added/deleted messages) since a given `historyId`. The `historyId` is stored in `Source.sync_cursor` (already exists). On first run with no cursor, falls back to current `messages.list`.

**Step 1: Write failing test**

```python
# tests/unit/test_gmail_history_poller.py
from unittest.mock import MagicMock, patch
from connectors.gmail.poller import _extract_new_message_ids_from_history


def test_extract_history_returns_added_ids():
    history = [
        {"messagesAdded": [{"message": {"id": "abc"}}, {"message": {"id": "def"}}]},
        {"messagesAdded": [{"message": {"id": "ghi"}}]},
        {"labelsAdded": [{"message": {"id": "xyz"}}]},  # ignored
    ]
    result = _extract_new_message_ids_from_history(history)
    assert result == ["abc", "def", "ghi"]


def test_extract_history_empty():
    assert _extract_new_message_ids_from_history([]) == []
```

**Step 2: Run test to verify it fails**
```bash
python3 -m pytest tests/unit/test_gmail_history_poller.py -v
```
Expected: `ImportError` or `AttributeError`

**Step 3: Implement delta polling**

Replace the body of `packages/connectors/src/connectors/gmail/poller.py` with:

```python
"""Gmail polling connector — uses History API delta for fast incremental sync.

First poll (no cursor): fetches recent messages via messages.list.
Subsequent polls: uses history.list with stored historyId cursor for O(changes) calls.
"""
import base64
import time
from datetime import datetime, timezone

import structlog
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from connectors.gmail.auth import get_credentials
from core.config import get_settings
from core.db.engine import get_db
from core.db.models import RawEvent, Source

log = structlog.get_logger()


def _with_backoff(fn, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            return fn()
        except HttpError as exc:
            if exc.resp.status in (429, 403) and attempt < max_retries - 1:
                wait = 2 ** attempt
                log.warning("gmail_quota_backoff", attempt=attempt, wait_seconds=wait)
                time.sleep(wait)
            else:
                raise


def _build_service():
    creds = get_credentials()
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _extract_header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _extract_new_message_ids_from_history(history: list[dict]) -> list[str]:
    """Pull message IDs from messagesAdded events in a history response."""
    ids = []
    for entry in history:
        for added in entry.get("messagesAdded", []):
            msg_id = added.get("message", {}).get("id")
            if msg_id:
                ids.append(msg_id)
    return ids


def _fetch_message_ids_delta(service, history_id: str) -> tuple[list[str], str]:
    """Fetch new message IDs since history_id. Returns (ids, new_history_id)."""
    all_history = []
    page_token = None
    new_history_id = history_id

    while True:
        kwargs = {"userId": "me", "startHistoryId": history_id, "historyTypes": ["messageAdded"]}
        if page_token:
            kwargs["pageToken"] = page_token
        resp = _with_backoff(lambda: service.users().history().list(**kwargs).execute())
        all_history.extend(resp.get("history", []))
        new_history_id = resp.get("historyId", new_history_id)
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return _extract_new_message_ids_from_history(all_history), new_history_id


def _fetch_message_ids_initial(service, max_results: int) -> tuple[list[str], str]:
    """Initial fetch: list recent messages + get current historyId."""
    settings = get_settings()
    label_filter = settings.llm_label_filter or ["INBOX"]
    resp = _with_backoff(lambda: service.users().messages().list(
        userId="me",
        labelIds=label_filter,
        maxResults=max_results,
    ).execute())
    ids = [m["id"] for m in resp.get("messages", [])]
    # Get current historyId from profile
    profile = service.users().getProfile(userId="me").execute()
    return ids, profile.get("historyId", "")


def _fetch_and_store_message(service, external_id: str, user_id: str, source_id: str) -> bool:
    """Fetch full message and insert as RawEvent. Returns True if inserted."""
    msg = _with_backoff(
        lambda: service.users().messages().get(
            userId="me", id=external_id, format="full"
        ).execute()
    )
    headers = msg.get("payload", {}).get("headers", [])
    label_ids = msg.get("labelIds", [])

    with get_db() as db:
        exists = db.query(RawEvent).filter_by(
            user_id=user_id, source_id=source_id, external_id=external_id
        ).first()
        if exists:
            return False

        db.add(RawEvent(
            user_id=user_id,
            source_id=source_id,
            external_id=external_id,
            payload_json={
                "id": external_id,
                "headers": {h["name"]: h["value"] for h in headers},
                "label_ids": label_ids,
                "snippet": msg.get("snippet", ""),
                "internal_date": msg.get("internalDate"),
                "payload": msg.get("payload", {}),
            },
        ))
        db.commit()
        log.info("raw_event_inserted", external_id=external_id, user_id=user_id)
    return True


def poll_gmail(user_id: str, source_id: str) -> int:
    """
    Poll Gmail for new messages. Uses History API if cursor exists, else initial fetch.
    Returns count of new raw_events inserted.
    """
    settings = get_settings()
    service = _build_service()
    inserted = 0

    with get_db() as db:
        source = db.query(Source).filter_by(id=source_id).first()
        history_id = source.sync_cursor if source else None

    if history_id:
        try:
            msg_ids, new_history_id = _fetch_message_ids_delta(service, history_id)
        except HttpError as exc:
            if exc.resp.status == 404:
                # historyId expired (>30 days old) — fall back to initial fetch
                log.warning("gmail_history_expired_falling_back", source_id=source_id)
                msg_ids, new_history_id = _fetch_message_ids_initial(service, settings.gmail_max_results)
            else:
                raise
    else:
        msg_ids, new_history_id = _fetch_message_ids_initial(service, settings.gmail_max_results)

    for external_id in msg_ids:
        if _fetch_and_store_message(service, external_id, user_id, source_id):
            inserted += 1

    # Update cursor and last_synced_at
    with get_db() as db:
        source = db.query(Source).filter_by(id=source_id).first()
        if source:
            source.sync_cursor = new_history_id
            source.last_synced_at = datetime.now(tz=timezone.utc)
            db.commit()

    log.info("gmail_poll_complete", inserted=inserted, source_id=source_id, user_id=user_id)
    return inserted
```

**Step 4: Update poll interval default to 2 minutes**

In `packages/core/src/core/config.py`:
```python
gmail_poll_interval_minutes: int = Field(default=2)  # was 15
```

**Step 5: Run tests**
```bash
python3 -m pytest tests/unit/test_gmail_history_poller.py tests/unit/ -v
```
Expected: all passing including new tests.

**Step 6: Smoke test**
```bash
claw sync  # should log gmail_poll_complete with historyId cursor stored
claw sync  # second run should use history delta (near-instant if no new mail)
```

**Step 7: Commit**
```bash
git add packages/connectors/src/connectors/gmail/poller.py packages/core/src/core/config.py tests/unit/test_gmail_history_poller.py
git commit -m "feat: gmail history api delta polling, 2-min interval"
```

---

## Task 3: Two-Stage LLM Triage

**Why:** 60-70% of emails have no actionable items (receipts, newsletters, notifications). A cheap Stage 1 call (Gemini 2.5 Flash-Lite, ~20 input tokens) gates the expensive Stage 2 extraction. Expected token cost reduction: 50-70%.

**Files:**
- Modify: `packages/core/src/core/llm/extractor.py`
- Modify: `packages/core/src/core/config.py`

**Step 1: Add config fields**

In `packages/core/src/core/config.py`, add after `llm_mode`:
```python
llm_triage_enabled: bool = Field(default=True)
llm_triage_model: str = Field(default="gemini-2.5-flash-lite")
```

**Step 2: Write failing test**

```python
# tests/unit/test_llm_triage.py
from unittest.mock import patch, MagicMock
from core.llm.extractor import _is_actionable


def test_triage_returns_true_for_actionable():
    with patch("core.llm.extractor._call_llm_raw") as mock_llm:
        mock_llm.return_value = '{"actionable": true}'
        result = _is_actionable("Prof Tan", "Assignment due tomorrow", "Submit report by Friday 11:59pm")
        assert result is True


def test_triage_returns_false_for_receipt():
    with patch("core.llm.extractor._call_llm_raw") as mock_llm:
        mock_llm.return_value = '{"actionable": false}'
        result = _is_actionable("grab@grab.com", "Your receipt", "Total: $12.50")
        assert result is False


def test_triage_defaults_true_on_llm_error():
    """Fail open — if triage LLM errors, proceed with full extraction."""
    with patch("core.llm.extractor._call_llm_raw", side_effect=Exception("timeout")):
        result = _is_actionable("anyone@example.com", "subject", "body")
        assert result is True
```

**Step 3: Run test to verify it fails**
```bash
python3 -m pytest tests/unit/test_llm_triage.py -v
```

**Step 4: Implement triage**

Add to `packages/core/src/core/llm/extractor.py` after existing imports:

```python
_TRIAGE_SYSTEM = (
    "You are a triage filter. Respond with JSON only: {\"actionable\": true/false}. "
    "An email is actionable if it requires the user to DO something: reply, submit, pay, attend, review, or decide. "
    "Receipts, newsletters, automated notifications with no action required = false."
)

_TRIAGE_USER = "From: {sender}\nSubject: {subject}\nPreview: {preview}"


def _is_actionable(sender: str, subject: str, preview: str) -> bool:
    """Stage 1 triage: cheap LLM call to decide if email warrants full extraction."""
    settings = get_settings()
    user_prompt = _TRIAGE_USER.format(sender=sender, subject=subject, preview=preview[:200])
    try:
        raw = _call_llm_raw(
            _TRIAGE_SYSTEM,
            user_prompt,
            model_override=settings.llm_triage_model,
        )
        return json.loads(raw).get("actionable", True)
    except Exception:
        return True  # fail open
```

Also add `_call_llm_raw` — a version of `_call_llm` that accepts a model override and returns just the text (no token counting needed for triage):

```python
def _call_llm_raw(system: str, user: str, model_override: str | None = None) -> str:
    """Call LLM with optional model override, return raw text response."""
    settings = get_settings()
    provider = settings.llm_provider
    model = model_override or (
        settings.gemini_model if provider == "gemini" else settings.anthropic_model
    )
    if provider == "gemini":
        raw, _, _ = _call_gemini(system, user, model=model)
    else:
        raw, _, _ = _call_anthropic(system, user, model=model)
    return raw
```

Then modify `extract_message` to gate on triage. After line `body = msg.body_full or msg.body_preview`, add:

```python
        # Stage 1: cheap triage (skip if disabled)
        if settings.llm_triage_enabled:
            if not _is_actionable(msg.sender, msg.title, (body or "")[:300]):
                log.info("extraction_skipped_triage", message_id=message_id, sender=msg.sender)
                # Mark as "processed" so we don't retry it forever
                _record_triage_skip(db, message_id, prompt_version)
                return True
```

Add `_record_triage_skip` helper (writes a MessageSummary with `extraction_failed=True` and `summary_short="triage:skip"`):

```python
def _record_triage_skip(db, message_id: str, prompt_version: str) -> None:
    from core.db.models import MessageSummary
    from datetime import datetime, timezone
    db.add(MessageSummary(
        message_id=message_id,
        prompt_version=prompt_version,
        summary_short="triage:skip",
        urgency=0.0,
        extraction_failed=False,
    ))
    db.commit()
```

**Step 5: Run tests**
```bash
python3 -m pytest tests/unit/test_llm_triage.py tests/unit/ -v
```

**Step 6: Smoke test** (watch for `extraction_skipped_triage` in logs)
```bash
LLM_LABEL_FILTER=[] claw sync
```

**Step 7: Commit**
```bash
git add packages/core/src/core/llm/extractor.py packages/core/src/core/config.py tests/unit/test_llm_triage.py
git commit -m "feat: two-stage llm triage gate (gemini-2.5-flash-lite pre-filter)"
```

---

## Task 4: `claw today` Morning Briefing

**Why:** Single command for a quick morning check — due today, next reminder, today's PVI score, upcoming calendar events. Faster than running 4 separate commands.

**Files:**
- Create: `packages/cli/src/cli/commands/today.py`
- Modify: `packages/cli/src/cli/main.py`

**Step 1: Implement command**

```python
# packages/cli/src/cli/commands/today.py
"""claw today — morning briefing: tasks due today, next reminder, PVI, upcoming events."""
from datetime import datetime, timezone, timedelta
from rich.console import Console
from rich.table import Table
from rich import print as rprint

console = Console()


def cmd_today():
    """Quick morning briefing — due today, reminders, PVI, calendar."""
    from core.db.engine import get_db
    from core.db.models import ActionItem, Reminder, PVIDailyScore, CalendarEvent
    from core.config import get_settings

    settings = get_settings()
    now = datetime.now(tz=timezone.utc)
    today = now.date()
    tomorrow = today + timedelta(days=1)
    uid = settings.default_user_id

    with get_db() as db:
        # Tasks due today or overdue
        due_today = db.query(ActionItem).filter(
            ActionItem.user_id == uid,
            ActionItem.status.in_(["proposed", "active"]),
            ActionItem.due_at < datetime(tomorrow.year, tomorrow.month, tomorrow.day, tzinfo=timezone.utc),
        ).order_by(ActionItem.due_at).all()

        # Next 3 reminders
        next_reminders = db.query(Reminder).filter(
            Reminder.user_id == uid,
            Reminder.status == "pending",
            Reminder.remind_at >= now,
        ).order_by(Reminder.remind_at).limit(3).all()

        # Today's PVI
        pvi = db.query(PVIDailyScore).filter_by(user_id=uid, date=today).first()

        # Upcoming calendar events (next 24h)
        upcoming_events = db.query(CalendarEvent).filter(
            CalendarEvent.user_id == uid,
            CalendarEvent.start_at >= now,
            CalendarEvent.start_at < now + timedelta(hours=24),
        ).order_by(CalendarEvent.start_at).limit(5).all()

        rprint(f"\n[bold cyan]☀ Good morning — {today.strftime('%A, %d %B %Y')}[/bold cyan]\n")

        # PVI
        if pvi:
            regime_colour = {"calm": "green", "normal": "cyan", "surge": "yellow", "crisis": "red"}.get(pvi.regime, "white")
            rprint(f"[bold]PVI:[/bold] [{regime_colour}]{pvi.score} ({pvi.regime})[/{regime_colour}]  {pvi.explanation[:80]}\n")

        # Tasks due
        if due_today:
            t = Table(title="Due Today", box=None, padding=(0, 2))
            t.add_column("Task")
            t.add_column("Due", style="dim")
            t.add_column("Status")
            for task in due_today:
                due_str = task.due_at.strftime("%H:%M") if task.due_at else "no time"
                overdue = task.due_at and task.due_at < now
                status_str = "[red]OVERDUE[/red]" if overdue else task.status
                t.add_row(task.title[:50], due_str, status_str)
            console.print(t)
        else:
            rprint("[green]✓ Nothing due today[/green]")

        # Next reminders
        if next_reminders:
            rprint("\n[bold]Next reminders:[/bold]")
            for r in next_reminders:
                delta_min = int((r.remind_at - now).total_seconds() / 60)
                in_str = f"{delta_min}m" if delta_min < 60 else f"{delta_min // 60}h"
                rprint(f"  ⏰ in {in_str} — {r.channel}")

        # Calendar
        if upcoming_events:
            rprint("\n[bold]Upcoming (24h):[/bold]")
            for ev in upcoming_events:
                start = ev.start_at.strftime("%H:%M")
                rprint(f"  📅 {start} — {ev.title[:50]}")

        rprint("")
```

**Step 2: Register in main.py**

```python
from cli.commands.today import cmd_today
app.command("today")(cmd_today)
```

**Step 3: Smoke test**
```bash
claw today
```

**Step 4: Commit**
```bash
git add packages/cli/src/cli/commands/today.py packages/cli/src/cli/main.py
git commit -m "feat: claw today morning briefing command"
```

---

## Task 5: Focus / DND Mode

**Why:** During deep work sessions, Telegram reminders are distracting. `claw focus 2h` silences Telegram delivery while still storing reminders. `claw focus end` resumes.

**Files:**
- Create: `packages/cli/src/cli/commands/focus.py`
- Modify: `packages/cli/src/cli/main.py`
- Modify: `packages/core/src/core/pipeline/reminders.py`

**Step 1: Write failing test**

```python
# tests/unit/test_focus_mode.py
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta


def test_is_in_focus_returns_true_during_active_session():
    from core.pipeline.reminders import _is_in_focus
    mock_db = MagicMock()
    mock_session = MagicMock()
    mock_session.ends_at = datetime.now(tz=timezone.utc) + timedelta(hours=1)
    mock_session.is_active = True
    mock_db.query.return_value.filter.return_value.first.return_value = mock_session
    assert _is_in_focus(mock_db, "user-id") is True


def test_is_in_focus_returns_false_when_no_session():
    from core.pipeline.reminders import _is_in_focus
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    assert _is_in_focus(mock_db, "user-id") is False
```

**Step 2: Implement `_is_in_focus` in reminders.py**

Add to `packages/core/src/core/pipeline/reminders.py`:

```python
def _is_in_focus(db, user_id: str) -> bool:
    """Return True if user has an active, unexpired focus session."""
    from core.db.models import FocusSession
    from datetime import datetime, timezone
    now = datetime.now(tz=timezone.utc)
    session = db.query(FocusSession).filter(
        FocusSession.user_id == user_id,
        FocusSession.is_active == True,
        FocusSession.ends_at > now,
    ).first()
    return session is not None
```

Then in `dispatch_due_reminders`, gate Telegram sends:
```python
# Inside the reminder dispatch loop, before sending Telegram:
if reminder.channel == "telegram":
    if _is_in_focus(db, str(reminder.user_id)):
        log.info("reminder_suppressed_focus_mode", reminder_id=reminder.id)
        continue
```

**Step 3: Implement CLI command**

```python
# packages/cli/src/cli/commands/focus.py
"""claw focus — DND mode: silence Telegram reminders for a set duration."""
import typer
from datetime import datetime, timezone, timedelta
from rich import print as rprint
from rich.console import Console

app = typer.Typer()
console = Console()


@app.command("start")
def focus_start(
    duration: str = typer.Argument("1h", help="Duration: 30m, 2h, 90m"),
):
    """Start a focus session (silences Telegram reminders)."""
    from core.db.engine import get_db
    from core.db.models import FocusSession
    from core.config import get_settings

    settings = get_settings()
    now = datetime.now(tz=timezone.utc)

    # Parse duration string: "2h", "30m", "90m"
    duration = duration.strip().lower()
    if duration.endswith("h"):
        minutes = int(duration[:-1]) * 60
    elif duration.endswith("m"):
        minutes = int(duration[:-1])
    else:
        rprint("[red]Invalid duration. Use format: 30m, 2h, 90m[/red]")
        raise typer.Exit(1)

    ends_at = now + timedelta(minutes=minutes)

    with get_db() as db:
        # Deactivate any existing focus sessions
        from sqlalchemy import update
        db.query(FocusSession).filter(
            FocusSession.user_id == settings.default_user_id,
            FocusSession.is_active == True,
        ).update({"is_active": False})
        db.add(FocusSession(
            user_id=settings.default_user_id,
            ends_at=ends_at,
            is_active=True,
        ))
        db.commit()

    rprint(f"[green]🎯 Focus mode ON until {ends_at.strftime('%H:%M')} UTC ({minutes}min)[/green]")
    rprint("[dim]Telegram reminders silenced. Run: claw focus end — to stop early.[/dim]")


@app.command("status")
def focus_status():
    """Show current focus session status."""
    from core.db.engine import get_db
    from core.db.models import FocusSession
    from core.config import get_settings

    settings = get_settings()
    now = datetime.now(tz=timezone.utc)

    with get_db() as db:
        session = db.query(FocusSession).filter(
            FocusSession.user_id == settings.default_user_id,
            FocusSession.is_active == True,
            FocusSession.ends_at > now,
        ).first()

        if not session:
            rprint("[dim]No active focus session.[/dim]")
        else:
            remaining = int((session.ends_at - now).total_seconds() / 60)
            rprint(f"[green]🎯 Focus mode active — {remaining}min remaining (ends {session.ends_at.strftime('%H:%M')} UTC)[/green]")


@app.command("end")
def focus_end():
    """End the current focus session early."""
    from core.db.engine import get_db
    from core.db.models import FocusSession
    from core.config import get_settings

    settings = get_settings()
    now = datetime.now(tz=timezone.utc)

    with get_db() as db:
        updated = db.query(FocusSession).filter(
            FocusSession.user_id == settings.default_user_id,
            FocusSession.is_active == True,
        ).update({"is_active": False, "ended_early_at": now})
        db.commit()

    if updated:
        rprint("[yellow]Focus mode ended.[/yellow]")
    else:
        rprint("[dim]No active focus session to end.[/dim]")
```

**Step 4: Register in main.py**
```python
from cli.commands import focus
app.add_typer(focus.app, name="focus", help="Focus/DND mode — silence Telegram reminders")
```

**Step 5: Run tests**
```bash
python3 -m pytest tests/unit/test_focus_mode.py tests/unit/ -v
```

**Step 6: Smoke test**
```bash
claw focus start 30m
claw focus status
claw focus end
```

**Step 7: Commit**
```bash
git add packages/cli/src/cli/commands/focus.py packages/cli/src/cli/main.py packages/core/src/core/pipeline/reminders.py tests/unit/test_focus_mode.py
git commit -m "feat: focus/dnd mode — silence telegram reminders during deep work"
```

---

## Task 6: Microsoft Graph Connector — Auth (MSAL Device Code)

**Why:** Microsoft Graph covers Outlook personal + any Microsoft 365 tenant (including NUS `aryan.ganju@u.nus.edu`). Device code flow works for desktop without a redirect URI server.

**Prerequisites:**
1. Install MSAL: `pip install msal` (add to `packages/connectors/pyproject.toml` dependencies)
2. Register Azure App:
   - Go to https://portal.azure.com → Azure Active Directory → App registrations → New registration
   - Name: "Clawdbot", Supported account types: **Accounts in any organizational directory AND personal Microsoft accounts**
   - Redirect URI: leave blank (device code flow doesn't need it)
   - After creation: note the **Application (client) ID**
   - API permissions → Add → Microsoft Graph → Delegated: `Mail.Read`, `Calendars.Read`, `User.Read` → Grant admin consent (or user consent on first login)
   - Authentication → Advanced settings → Allow public client flows: **Yes**
3. Add to `.env`:
   ```
   OUTLOOK_CLIENT_ID=<your-azure-app-client-id>
   ```

**Files:**
- Create: `packages/connectors/src/connectors/outlook/__init__.py`
- Create: `packages/connectors/src/connectors/outlook/auth.py`
- Modify: `packages/connectors/pyproject.toml`
- Modify: `packages/core/src/core/config.py`

**Step 1: Add config field**

In `packages/core/src/core/config.py`:
```python
# Microsoft Graph / Outlook
outlook_client_id: str = Field(default="")
outlook_token_service: str = Field(default="clawdbot-outlook")
```

**Step 2: Add msal dependency**

In `packages/connectors/pyproject.toml`:
```toml
dependencies = [
    "core",
    "google-auth>=2.29",
    "google-auth-oauthlib>=1.2",
    "google-api-python-client>=2.125",
    "beautifulsoup4>=4.12",
    "lxml>=5.0",
    "msal>=1.28",
]
```

Install: `pip install msal`

**Step 3: Implement auth module**

```python
# packages/connectors/src/connectors/outlook/__init__.py
```

```python
# packages/connectors/src/connectors/outlook/auth.py
"""Microsoft Graph authentication via MSAL device code flow.

Works for personal Outlook accounts AND any Microsoft 365 tenant (NUS, corp).
Device code flow: user visits a URL and enters a code — no redirect URI server needed.
"""
import json
from datetime import datetime, timezone

import msal
import structlog

from core.config import get_settings
from core.tokens import store_token, get_token

log = structlog.get_logger()

SCOPES = ["Mail.Read", "Calendars.Read", "User.Read", "offline_access"]
AUTHORITY = "https://login.microsoftonline.com/common"


def _build_app() -> msal.PublicClientApplication:
    settings = get_settings()
    if not settings.outlook_client_id:
        raise RuntimeError(
            "OUTLOOK_CLIENT_ID not set in .env. "
            "Register an Azure app at https://portal.azure.com"
        )
    return msal.PublicClientApplication(
        client_id=settings.outlook_client_id,
        authority=AUTHORITY,
    )


def run_oauth_flow() -> dict:
    """
    Run MSAL device code flow. Prints instructions for user to authenticate.
    Returns token dict stored in keyring.
    """
    settings = get_settings()
    app = _build_app()

    # Check for cached token first
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            store_token(settings.outlook_token_service, "default", result)
            log.info("outlook_token_refreshed_from_cache")
            return result

    # Device code flow
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(f"Device flow failed: {flow.get('error_description')}")

    print(f"\n{flow['message']}\n")  # Prints: "Go to https://microsoft.com/devicelogin and enter code XXXX-XXXX"

    result = app.acquire_token_by_device_flow(flow)  # blocks until user authenticates
    if "access_token" not in result:
        raise RuntimeError(f"Auth failed: {result.get('error_description', result)}")

    store_token(settings.outlook_token_service, "default", result)
    log.info("outlook_oauth_complete")
    return result


def get_token_dict() -> dict:
    """Return cached token, refreshing if expired. Raises if not authenticated."""
    settings = get_settings()
    token = get_token(settings.outlook_token_service, "default")
    if not token:
        raise RuntimeError("Outlook not connected. Run: claw connect outlook")

    app = _build_app()
    # MSAL can refresh using the refresh_token stored in the dict
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            store_token(settings.outlook_token_service, "default", result)
            return result

    # Fallback: use stored token as-is (may be expired)
    return token
```

**Step 4: Write auth test**

```python
# tests/unit/test_outlook_auth.py
from unittest.mock import patch, MagicMock


def test_get_token_dict_raises_when_not_connected():
    with patch("connectors.outlook.auth.get_token", return_value=None):
        from connectors.outlook.auth import get_token_dict
        try:
            get_token_dict()
            assert False, "Should have raised"
        except RuntimeError as e:
            assert "not connected" in str(e).lower()
```

**Step 5: Run tests**
```bash
python3 -m pytest tests/unit/test_outlook_auth.py -v
```

**Step 6: Commit**
```bash
git add packages/connectors/src/connectors/outlook/ packages/connectors/pyproject.toml packages/core/src/core/config.py tests/unit/test_outlook_auth.py
git commit -m "feat: microsoft graph auth — msal device code flow for outlook + nus"
```

---

## Task 7: Microsoft Graph Connector — Outlook Mail Poller

**Files:**
- Create: `packages/connectors/src/connectors/outlook/poller.py`

**Background:** Graph API uses `$deltaLink` for incremental mail sync — same concept as Gmail historyId. First call returns all mail + a `@odata.deltaLink`. Subsequent calls to the deltaLink return only changes.

**Step 1: Write test**

```python
# tests/unit/test_outlook_poller.py
from connectors.outlook.poller import _extract_message_fields


def test_extract_message_fields_basic():
    graph_msg = {
        "id": "AAMk123",
        "subject": "Assignment due Friday",
        "from": {"emailAddress": {"address": "prof@nus.edu.sg", "name": "Prof Tan"}},
        "receivedDateTime": "2026-03-02T10:00:00Z",
        "bodyPreview": "Please submit by 11:59pm",
        "body": {"content": "<p>Please submit by 11:59pm</p>", "contentType": "html"},
        "isRead": False,
    }
    fields = _extract_message_fields(graph_msg)
    assert fields["external_id"] == "AAMk123"
    assert fields["sender"] == "prof@nus.edu.sg"
    assert fields["title"] == "Assignment due Friday"
    assert "submit" in fields["body_preview"]
```

**Step 2: Implement poller**

```python
# packages/connectors/src/connectors/outlook/poller.py
"""Outlook mail poller via Microsoft Graph delta sync."""
import re
from datetime import datetime, timezone
from html.parser import HTMLParser

import httpx
import structlog

from connectors.outlook.auth import get_token_dict
from core.config import get_settings
from core.db.engine import get_db
from core.db.models import RawEvent, Source

log = structlog.get_logger()

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
MAIL_DELTA_URL = f"{GRAPH_BASE}/me/mailFolders/inbox/messages/delta"


class _HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._text = []

    def handle_data(self, data):
        self._text.append(data)

    def get_text(self):
        return " ".join(self._text).strip()


def _strip_html(html: str) -> str:
    s = _HTMLStripper()
    s.feed(html)
    return s.get_text()


def _extract_message_fields(graph_msg: dict) -> dict:
    """Normalise a Graph API message object into our field names."""
    sender_info = graph_msg.get("from", {}).get("emailAddress", {})
    body = graph_msg.get("body", {})
    body_text = _strip_html(body.get("content", "")) if body.get("contentType") == "html" else body.get("content", "")

    return {
        "external_id": graph_msg["id"],
        "sender": sender_info.get("address", "unknown"),
        "sender_name": sender_info.get("name", ""),
        "title": graph_msg.get("subject", "(no subject)"),
        "body_preview": graph_msg.get("bodyPreview", "")[:500],
        "body_full": body_text[:10000],
        "received_at": graph_msg.get("receivedDateTime", ""),
        "is_read": graph_msg.get("isRead", False),
        "categories": graph_msg.get("categories", []),
    }


def _graph_get(url: str, token: dict) -> dict:
    headers = {"Authorization": f"Bearer {token['access_token']}", "Accept": "application/json"}
    resp = httpx.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def poll_outlook(user_id: str, source_id: str) -> int:
    """
    Poll Outlook inbox via Graph delta sync.
    Stores deltaLink as sync_cursor on Source.
    Returns count of new raw_events inserted.
    """
    token = get_token_dict()
    inserted = 0

    with get_db() as db:
        source = db.query(Source).filter_by(id=source_id).first()
        delta_link = source.sync_cursor if source else None

    # Use stored deltaLink or start fresh
    url = delta_link or (MAIL_DELTA_URL + "?$select=id,subject,from,receivedDateTime,bodyPreview,body,isRead,categories&$top=50")
    new_delta_link = None

    while url:
        data = _graph_get(url, token)
        messages = data.get("value", [])

        for msg in messages:
            if msg.get("@odata.type") == "#microsoft.graph.message":
                fields = _extract_message_fields(msg)
                with get_db() as db:
                    exists = db.query(RawEvent).filter_by(
                        user_id=user_id, source_id=source_id, external_id=fields["external_id"]
                    ).first()
                    if not exists:
                        db.add(RawEvent(
                            user_id=user_id,
                            source_id=source_id,
                            external_id=fields["external_id"],
                            payload_json=fields,
                        ))
                        db.commit()
                        log.info("outlook_message_inserted", external_id=fields["external_id"][:12])
                        inserted += 1

        next_link = data.get("@odata.nextLink")
        new_delta_link = data.get("@odata.deltaLink", new_delta_link)
        url = next_link  # None when pagination exhausted

    # Save deltaLink as cursor
    if new_delta_link:
        with get_db() as db:
            source = db.query(Source).filter_by(id=source_id).first()
            if source:
                source.sync_cursor = new_delta_link
                source.last_synced_at = datetime.now(tz=timezone.utc)
                db.commit()

    log.info("outlook_poll_complete", inserted=inserted, source_id=source_id, user_id=user_id)
    return inserted
```

**Step 3: Run tests**
```bash
python3 -m pytest tests/unit/test_outlook_poller.py tests/unit/ -v
```

**Step 4: Commit**
```bash
git add packages/connectors/src/connectors/outlook/poller.py tests/unit/test_outlook_poller.py
git commit -m "feat: outlook graph mail poller with delta sync"
```

---

## Task 8: `claw connect outlook` + Worker Job

**Files:**
- Modify: `packages/cli/src/cli/commands/connect.py`
- Modify: `apps/worker/src/worker/jobs.py`
- Modify: `apps/worker/src/worker/main.py`

**Step 1: Add `claw connect outlook` command**

In `packages/cli/src/cli/commands/connect.py`, add a new sub-command:

```python
@app.command("outlook")
def connect_outlook():
    """Authenticate with Microsoft Graph (Outlook + NUS email)."""
    from connectors.outlook.auth import run_oauth_flow
    from core.db.engine import get_db
    from core.db.models import Source, User
    from core.config import get_settings
    from rich import print as rprint

    settings = get_settings()
    rprint("[bold]Connecting Outlook via Microsoft Graph...[/bold]")
    rprint("[dim]You will be prompted to open a URL and enter a short code.[/dim]\n")

    try:
        run_oauth_flow()
    except Exception as e:
        rprint(f"[red]Auth failed: {e}[/red]")
        raise typer.Exit(1)

    # Register source in DB
    with get_db() as db:
        existing = db.query(Source).filter_by(
            user_id=settings.default_user_id, source_type="outlook"
        ).first()
        if not existing:
            db.add(Source(
                user_id=settings.default_user_id,
                source_type="outlook",
                display_name="Outlook/NUS",
                config_json={},
            ))
            db.commit()
            rprint("[green]✓ Outlook connected and registered.[/green]")
        else:
            rprint("[green]✓ Outlook token refreshed.[/green]")
```

**Step 2: Add worker job**

In `apps/worker/src/worker/jobs.py`, add:

```python
def job_poll_outlook():
    from connectors.outlook.poller import poll_outlook
    from core.db.engine import get_db
    from core.db.models import Source
    from core.config import get_settings

    settings = get_settings()
    with get_db() as db:
        sources = db.query(Source).filter_by(source_type="outlook").all()
        pairs = [(str(s.user_id), str(s.id)) for s in sources]

    for user_id, source_id in pairs:
        poll_outlook(user_id, source_id)
```

**Step 3: Add to scheduler**

In `apps/worker/src/worker/main.py`:
```python
from worker.jobs import job_poll_outlook

scheduler.add_job(
    job_poll_outlook,
    IntervalTrigger(minutes=2),
    id="poll_outlook",
)
```

**Step 4: Normalizer compatibility**

The existing normalizer (`normalize_all_pending`) reads `raw_events.payload_json`. For Outlook, the payload has `sender`, `title`, `body_preview`, `body_full` fields directly (vs Gmail's nested header structure). Update `packages/core/src/core/pipeline/normalizer.py` to handle both:

Check what field name to use by inspecting `payload_json.get("sender")` (Outlook format) vs `payload_json.get("headers", {}).get("From")` (Gmail format). The normalizer should detect which format is present.

```python
def _parse_sender(payload: dict) -> str:
    # Outlook format
    if "sender" in payload:
        return payload["sender"]
    # Gmail format
    headers = payload.get("headers", {})
    return headers.get("From") or headers.get("from") or "unknown"

def _parse_title(payload: dict) -> str:
    if "title" in payload:
        return payload["title"]
    headers = payload.get("headers", {})
    return headers.get("Subject") or headers.get("subject") or "(no subject)"

def _parse_body(payload: dict) -> tuple[str, str]:
    """Returns (body_preview, body_full)."""
    if "body_full" in payload:
        return payload.get("body_preview", ""), payload["body_full"]
    # Gmail: decode from payload parts
    return _extract_gmail_body(payload)
```

**Step 5: Smoke test**
```bash
claw connect outlook    # authenticate
claw sync               # won't poll outlook yet — need to update sync.py
```

Also update `packages/cli/src/cli/commands/sync.py` to poll outlook sources:
```python
# After Gmail polling:
from connectors.outlook.poller import poll_outlook
outlook_sources = db.query(Source).filter_by(source_type="outlook").all()
for s in outlook_sources:
    poll_outlook(str(s.user_id), str(s.id))
```

**Step 6: Commit**
```bash
git add packages/cli/src/cli/commands/connect.py apps/worker/src/worker/jobs.py apps/worker/src/worker/main.py packages/core/src/core/pipeline/normalizer.py packages/cli/src/cli/commands/sync.py
git commit -m "feat: claw connect outlook, worker job, normalizer multi-source support"
```

---

## Task 9: Google Calendar Connector

**Files:**
- Create: `packages/connectors/src/connectors/gcal/__init__.py`
- Create: `packages/connectors/src/connectors/gcal/poller.py`

**Background:** Uses the same Google OAuth credentials as Gmail (add `calendar.readonly` scope). Fetches events in the next 14 days on each poll.

**Step 1: Update Gmail OAuth scope**

In `packages/connectors/src/connectors/gmail/auth.py`, add the calendar scope:
```python
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.labels",
    "https://www.googleapis.com/auth/calendar.readonly",
]
```

⚠️ After adding this scope, the existing Gmail token will be invalid (scope mismatch). User must re-run `claw connect gmail` to re-authenticate with the new scope.

**Step 2: Write test**

```python
# tests/unit/test_gcal_poller.py
from connectors.gcal.poller import _parse_event_fields


def test_parse_event_fields_timed():
    event = {
        "id": "abc123",
        "summary": "CS3230 Lecture",
        "start": {"dateTime": "2026-03-05T10:00:00+08:00"},
        "end": {"dateTime": "2026-03-05T12:00:00+08:00"},
        "location": "LT19",
        "attendees": [{"email": "a@nus.edu.sg"}],
        "description": "Week 8 lecture",
    }
    fields = _parse_event_fields(event)
    assert fields["external_id"] == "abc123"
    assert fields["title"] == "CS3230 Lecture"
    assert fields["is_all_day"] is False
    assert fields["location"] == "LT19"


def test_parse_event_fields_all_day():
    event = {
        "id": "def456",
        "summary": "Holiday",
        "start": {"date": "2026-03-10"},
        "end": {"date": "2026-03-11"},
    }
    fields = _parse_event_fields(event)
    assert fields["is_all_day"] is True
```

**Step 3: Implement poller**

```python
# packages/connectors/src/connectors/gcal/__init__.py
```

```python
# packages/connectors/src/connectors/gcal/poller.py
"""Google Calendar connector — polls next 14 days of events."""
import json
from datetime import datetime, timezone, timedelta

import structlog
from googleapiclient.discovery import build

from connectors.gmail.auth import get_credentials
from core.db.engine import get_db
from core.db.models import CalendarEvent, Source
from core.config import get_settings

log = structlog.get_logger()


def _parse_event_fields(event: dict) -> dict:
    start = event.get("start", {})
    end = event.get("end", {})
    is_all_day = "date" in start and "dateTime" not in start

    def parse_dt(dt_dict: dict) -> datetime:
        if "dateTime" in dt_dict:
            return datetime.fromisoformat(dt_dict["dateTime"]).astimezone(timezone.utc)
        # all-day event: use date at midnight UTC
        d = dt_dict["date"]
        return datetime.fromisoformat(d + "T00:00:00+00:00")

    return {
        "external_id": event["id"],
        "title": event.get("summary", "(no title)"),
        "start_at": parse_dt(start),
        "end_at": parse_dt(end),
        "location": event.get("location"),
        "attendees_json": [a.get("email") for a in event.get("attendees", [])],
        "description": event.get("description"),
        "is_all_day": is_all_day,
    }


def poll_gcal(user_id: str, source_id: str) -> int:
    """Fetch events for next 14 days. Upsert CalendarEvent rows. Returns insert count."""
    settings = get_settings()
    creds = get_credentials()
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    now = datetime.now(tz=timezone.utc)
    time_min = now.isoformat()
    time_max = (now + timedelta(days=14)).isoformat()

    events_result = service.events().list(
        calendarId="primary",
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy="startTime",
        maxResults=50,
    ).execute()

    events = events_result.get("items", [])
    inserted = 0

    for event in events:
        if event.get("status") == "cancelled":
            continue
        fields = _parse_event_fields(event)
        with get_db() as db:
            existing = db.query(CalendarEvent).filter_by(
                user_id=user_id, external_id=fields["external_id"]
            ).first()
            if existing:
                # Update in case title/time changed
                for k, v in fields.items():
                    if k != "external_id":
                        setattr(existing, k, v)
                db.commit()
            else:
                db.add(CalendarEvent(user_id=user_id, source_id=source_id, **fields))
                db.commit()
                inserted += 1

    log.info("gcal_poll_complete", inserted=inserted, total=len(events), user_id=user_id)
    return inserted
```

**Step 4: Add `claw connect gcal` command**

In `packages/cli/src/cli/commands/connect.py`:
```python
@app.command("gcal")
def connect_gcal():
    """Connect Google Calendar (re-uses Gmail OAuth credentials — requires re-auth if scopes changed)."""
    from connectors.gmail.auth import run_oauth_flow
    from core.db.engine import get_db
    from core.db.models import Source
    from core.config import get_settings
    from rich import print as rprint

    settings = get_settings()
    rprint("[bold]Connecting Google Calendar (re-authenticating Gmail with calendar scope)...[/bold]")
    try:
        run_oauth_flow()
    except Exception as e:
        rprint(f"[red]Auth failed: {e}[/red]")
        raise typer.Exit(1)

    with get_db() as db:
        existing = db.query(Source).filter_by(
            user_id=settings.default_user_id, source_type="gcal"
        ).first()
        if not existing:
            db.add(Source(
                user_id=settings.default_user_id,
                source_type="gcal",
                display_name="Google Calendar",
                config_json={},
            ))
            db.commit()
    rprint("[green]✓ Google Calendar connected.[/green]")
    rprint("[dim]Run: claw sync — to pull in upcoming events.[/dim]")
```

**Step 5: Add to sync and worker**

`packages/cli/src/cli/commands/sync.py` — add after Outlook polling:
```python
from connectors.gcal.poller import poll_gcal
gcal_sources = db.query(Source).filter_by(source_type="gcal").all()
for s in gcal_sources:
    poll_gcal(str(s.user_id), str(s.id))
```

Worker job:
```python
def job_poll_gcal():
    from connectors.gcal.poller import poll_gcal
    from core.db.engine import get_db
    from core.db.models import Source
    with get_db() as db:
        sources = db.query(Source).filter_by(source_type="gcal").all()
        pairs = [(str(s.user_id), str(s.id)) for s in sources]
    for user_id, source_id in pairs:
        poll_gcal(user_id, source_id)
```

**Step 6: Run tests**
```bash
python3 -m pytest tests/unit/test_gcal_poller.py tests/unit/ -v
```

**Step 7: Commit**
```bash
git add packages/connectors/src/connectors/gcal/ packages/cli/src/cli/commands/connect.py packages/cli/src/cli/commands/sync.py apps/worker/src/worker/jobs.py tests/unit/test_gcal_poller.py
git commit -m "feat: google calendar connector — poll 14-day events, claw connect gcal"
```

---

## Task 10: Meeting Prep Summaries

**Why:** When a calendar event starts within 30 minutes, generate a brief prep summary from any related emails and send via Telegram.

**Files:**
- Create: `packages/core/src/core/calendar/prep.py`
- Modify: `apps/worker/src/worker/jobs.py`

**Step 1: Implement prep generator**

```python
# packages/core/src/core/calendar/prep.py
"""Meeting prep: detect imminent events and surface relevant context."""
from datetime import datetime, timezone, timedelta
import structlog

log = structlog.get_logger()


def generate_prep_for_upcoming(user_id: str) -> list[str]:
    """
    Check for events starting in 15-45 minutes.
    For each, generate a prep summary via LLM (sender emails matching event attendees/title).
    Returns list of Telegram-ready message strings.
    """
    from core.db.engine import get_db
    from core.db.models import CalendarEvent, Message
    from core.llm.extractor import _call_llm_raw

    now = datetime.now(tz=timezone.utc)
    window_start = now + timedelta(minutes=15)
    window_end = now + timedelta(minutes=45)

    messages = []

    with get_db() as db:
        upcoming = db.query(CalendarEvent).filter(
            CalendarEvent.user_id == user_id,
            CalendarEvent.start_at >= window_start,
            CalendarEvent.start_at <= window_end,
        ).all()

        for event in upcoming:
            # Find related emails (matching attendee emails or title keywords)
            keywords = event.title.split()[:3]
            related = db.query(Message).filter(
                Message.user_id == user_id,
                Message.sender.in_(event.attendees_json or []),
            ).order_by(Message.message_ts.desc()).limit(3).all()

            context = "\n".join(
                f"- {m.sender}: {m.title}: {m.body_preview[:100]}"
                for m in related
            ) or "No related emails found."

            prompt = (
                f"Meeting in ~30 minutes: '{event.title}'\n"
                f"Related emails:\n{context}\n\n"
                f"Write a 3-bullet prep summary (what to know, what to prepare, any open questions)."
            )
            try:
                summary = _call_llm_raw("You are a meeting prep assistant.", prompt)
                msg = f"📅 *{event.title}* in 30min\n{summary[:800]}"
                messages.append(msg)
                log.info("meeting_prep_generated", event_id=event.id[:8])
            except Exception as exc:
                log.warning("meeting_prep_failed", error=str(exc))

    return messages
```

**Step 2: Add worker job**

```python
# apps/worker/src/worker/jobs.py
def job_meeting_prep():
    from core.calendar.prep import generate_prep_for_upcoming
    from core.telegram_client import send_message
    from core.config import get_settings

    settings = get_settings()
    summaries = generate_prep_for_upcoming(settings.default_user_id)
    for msg in summaries:
        send_message(msg)
```

Add to scheduler (every 5 minutes is fine — prep is idempotent once sent):
```python
scheduler.add_job(job_meeting_prep, IntervalTrigger(minutes=5), id="meeting_prep")
```

**Step 3: Commit**
```bash
git add packages/core/src/core/calendar/prep.py apps/worker/src/worker/jobs.py apps/worker/src/worker/main.py
git commit -m "feat: meeting prep summaries — telegram alert 30min before calendar events"
```

---

## Task 11: Textual TUI Dashboard (`claw dash`)

**Why:** Live, keyboard-driven dashboard. Better than running claw today + claw tasks list + claw status separately.

**Files:**
- Create: `packages/cli/src/cli/commands/dash.py`
- Modify: `packages/cli/pyproject.toml` (add `textual>=0.60`)
- Modify: `packages/cli/src/cli/main.py`

**Step 1: Install textual**
```bash
pip install textual
```

Add to `packages/cli/pyproject.toml`:
```toml
"textual>=0.60",
```

**Step 2: Implement dashboard**

```python
# packages/cli/src/cli/commands/dash.py
"""claw dash — live Textual TUI dashboard."""
import typer
from datetime import datetime, timezone, timedelta


def cmd_dash():
    """Launch the live Clawdbot dashboard (press q to quit)."""
    from textual.app import App, ComposeResult
    from textual.widgets import Header, Footer, DataTable, Static, Label
    from textual.containers import Horizontal, Vertical
    from textual import work
    from core.db.engine import get_db
    from core.db.models import ActionItem, Reminder, PVIDailyScore, CalendarEvent
    from core.config import get_settings

    settings = get_settings()
    uid = settings.default_user_id

    class ClawdApp(App):
        CSS = """
        Screen { layout: grid; grid-size: 2; grid-gutter: 1; }
        #tasks { height: 100%; border: solid cyan; }
        #reminders { height: 100%; border: solid yellow; }
        #status { height: 8; border: solid green; dock: bottom; }
        """
        BINDINGS = [
            ("q", "quit", "Quit"),
            ("s", "sync", "Sync"),
            ("r", "refresh", "Refresh"),
        ]

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            with Horizontal():
                yield DataTable(id="tasks")
                yield DataTable(id="reminders")
            yield Static(id="status")
            yield Footer()

        def on_mount(self):
            self._setup_tables()
            self.refresh_data()
            self.set_interval(60, self.refresh_data)

        def _setup_tables(self):
            tasks_table = self.query_one("#tasks", DataTable)
            tasks_table.add_columns("Task", "Due", "Status")

            rem_table = self.query_one("#reminders", DataTable)
            rem_table.add_columns("Task", "In", "Channel")

        def refresh_data(self):
            now = datetime.now(tz=timezone.utc)
            today_end = datetime(now.year, now.month, now.day, tzinfo=timezone.utc) + timedelta(days=1)

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
                    status_str = "OVERDUE" if overdue else t.status
                    tasks_table.add_row(t.title[:35], due, status_str)

                reminders = db.query(Reminder).filter(
                    Reminder.user_id == uid,
                    Reminder.status == "pending",
                    Reminder.remind_at >= now,
                ).order_by(Reminder.remind_at).limit(15).all()

                for r in reminders:
                    delta = int((r.remind_at - now).total_seconds() / 60)
                    in_str = f"{delta}m" if delta < 60 else f"{delta // 60}h"
                    # Need task title — get from action_item_id
                    task = db.query(ActionItem).filter_by(id=r.action_item_id).first()
                    title = task.title[:30] if task else r.action_item_id[:8]
                    rem_table.add_row(title, in_str, r.channel)

                pvi = db.query(PVIDailyScore).filter_by(
                    user_id=uid, date=now.date()
                ).first()
                pvi_str = f"PVI: {pvi.score} ({pvi.regime})" if pvi else "PVI: —"

            status.update(
                f"[bold]{pvi_str}[/bold]  |  Tasks: {len(tasks)}  |  "
                f"Reminders: {len(reminders)}  |  Last refresh: {now.strftime('%H:%M:%S')}"
            )

        def action_sync(self):
            import subprocess
            subprocess.Popen(["claw", "sync"])
            self.notify("Sync triggered in background", severity="information")

        def action_refresh(self):
            self.refresh_data()

    ClawdApp().run()
```

**Step 3: Register**
```python
from cli.commands.dash import cmd_dash
app.command("dash")(cmd_dash)
```

**Step 4: Smoke test**
```bash
claw dash   # should open full-screen TUI, q to quit
```

**Step 5: Commit**
```bash
git add packages/cli/src/cli/commands/dash.py packages/cli/pyproject.toml packages/cli/src/cli/main.py
git commit -m "feat: textual tui dashboard (claw dash) — live tasks, reminders, pvi"
```

---

## Task 12: Weekly Review Digest

**Files:**
- Create: `packages/core/src/core/digest/weekly.py`
- Modify: `packages/cli/src/cli/commands/digest.py`

**Step 1: Implement weekly generator**

```python
# packages/core/src/core/digest/weekly.py
"""Weekly review digest — summary of the past 7 days."""
from datetime import datetime, timezone, timedelta, date
import structlog

log = structlog.get_logger()


def generate_weekly_review(user_id: str) -> str:
    from core.db.engine import get_db
    from core.db.models import ActionItem, PVIDailyScore, Message

    now = datetime.now(tz=timezone.utc)
    week_ago = now - timedelta(days=7)
    today = now.date()

    with get_db() as db:
        # Task stats
        all_tasks = db.query(ActionItem).filter(
            ActionItem.user_id == user_id,
            ActionItem.created_at >= week_ago,
        ).all()
        done = [t for t in all_tasks if t.status == "done"]
        overdue = [t for t in all_tasks if t.status == "active" and t.due_at and t.due_at < now]
        proposed = [t for t in all_tasks if t.status == "proposed"]

        # PVI trend (last 7 days)
        pvi_scores = db.query(PVIDailyScore).filter(
            PVIDailyScore.user_id == user_id,
            PVIDailyScore.date >= week_ago.date(),
        ).order_by(PVIDailyScore.date).all()

        # Emails processed
        emails_processed = db.query(Message).filter(
            Message.user_id == user_id,
            Message.ingested_at >= week_ago,
        ).count()

    # Build sparkline for PVI
    pvi_map = {p.date: p.score for p in pvi_scores}
    sparkline = ""
    for i in range(7):
        d = (now - timedelta(days=6 - i)).date()
        score = pvi_map.get(d)
        if score is None:
            sparkline += "·"
        elif score >= 80:
            sparkline += "█"
        elif score >= 60:
            sparkline += "▆"
        elif score >= 40:
            sparkline += "▄"
        else:
            sparkline += "▂"

    avg_pvi = sum(p.score for p in pvi_scores) / len(pvi_scores) if pvi_scores else 0
    completion_rate = len(done) / len(all_tasks) * 100 if all_tasks else 0

    lines = [
        f"# Weekly Review — {today.strftime('%d %b %Y')}",
        "",
        f"## Performance Index",
        f"PVI trend (7d): {sparkline}  avg: {avg_pvi:.0f}",
        "",
        f"## Tasks",
        f"✓ Completed: {len(done)}",
        f"⚠ Overdue: {len(overdue)}",
        f"○ Proposed (unreviewed): {len(proposed)}",
        f"Completion rate: {completion_rate:.0f}%",
        "",
        f"## Inbox",
        f"Emails processed: {emails_processed}",
        "",
    ]

    if overdue:
        lines.append("## Still Outstanding")
        for t in overdue[:5]:
            due = t.due_at.strftime("%d %b") if t.due_at else "—"
            lines.append(f"• {t.title[:60]} (due {due})")
        lines.append("")

    return "\n".join(lines)
```

**Step 2: Add `claw digest --weekly` flag**

In `packages/cli/src/cli/commands/digest.py`, modify `cmd_digest` to accept a `--weekly` flag and call `generate_weekly_review`.

**Step 3: Commit**
```bash
git add packages/core/src/core/digest/weekly.py packages/cli/src/cli/commands/digest.py
git commit -m "feat: weekly review digest (claw digest --weekly)"
```

---

## Task 13: Reply Drafting (`claw reply`)

**Note:** `reply_drafts` table already exists from MVP. The LLM extractor already generates draft replies but they aren't surfaced in the CLI yet.

**Files:**
- Create: `packages/cli/src/cli/commands/reply.py`
- Modify: `packages/cli/src/cli/main.py`

**Step 1: Implement command**

```python
# packages/cli/src/cli/commands/reply.py
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
    from core.config import get_settings

    settings = get_settings()

    with get_db() as db:
        drafts = db.query(ReplyDraft, Message).join(
            Message, ReplyDraft.message_id == Message.id
        ).filter(ReplyDraft.status == "proposed").limit(20).all()

        if not drafts:
            rprint("[dim]No reply drafts.[/dim]")
            raise typer.Exit(0)

        t = Table(title="Reply Drafts")
        t.add_column("Msg ID", style="dim")
        t.add_column("From")
        t.add_column("Subject")
        t.add_column("Tone")
        for draft, msg in drafts:
            t.add_row(msg.id[:8], msg.sender[:30], msg.title[:40], draft.tone)
        console.print(t)


@app.command("view")
def view_reply(msg_id: str = typer.Argument(help="Message ID prefix")):
    """View the draft reply for a message."""
    from core.db.engine import get_db
    from core.db.models import ReplyDraft, Message

    with get_db() as db:
        draft = db.query(ReplyDraft).join(Message).filter(
            Message.id.like(f"{msg_id}%"),
            ReplyDraft.status == "proposed",
        ).first()

        if not draft:
            rprint(f"[red]No draft for {msg_id}[/red]")
            raise typer.Exit(1)

        rprint(f"\n[bold]Tone:[/bold] {draft.tone}")
        rprint(f"\n[bold]Draft:[/bold]\n{draft.draft_text}\n")


@app.command("send")
def send_reply(
    msg_id: str = typer.Argument(help="Message ID prefix"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Send the draft reply via Gmail API."""
    from core.db.engine import get_db
    from core.db.models import ReplyDraft, Message

    with get_db() as db:
        draft_row = db.query(ReplyDraft).join(Message).filter(
            Message.id.like(f"{msg_id}%"),
            ReplyDraft.status == "proposed",
        ).first()
        msg = db.query(Message).filter(Message.id.like(f"{msg_id}%")).first()

        if not draft_row or not msg:
            rprint(f"[red]Draft not found for {msg_id}[/red]")
            raise typer.Exit(1)

        rprint(f"\n[bold]To:[/bold] {msg.sender}")
        rprint(f"[bold]Re:[/bold] {msg.title}")
        rprint(f"\n{draft_row.draft_text[:300]}...\n")

        if not confirm:
            confirmed = typer.confirm("Send this reply?")
            if not confirmed:
                rprint("[yellow]Cancelled.[/yellow]")
                raise typer.Exit(0)

        # Send via Gmail API
        try:
            from connectors.gmail.auth import get_credentials
            from googleapiclient.discovery import build
            import base64, email.mime.text

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
```

**Step 2: Register**
```python
from cli.commands import reply
app.add_typer(reply.app, name="reply", help="View and send LLM-drafted replies")
```

**Note:** Gmail `send` requires adding `gmail.send` scope to `SCOPES` in `gmail/auth.py` and re-authenticating.

**Step 3: Commit**
```bash
git add packages/cli/src/cli/commands/reply.py packages/cli/src/cli/main.py
git commit -m "feat: claw reply list/view/send — surface llm reply drafts"
```

---

## Task 14: Unit Tests for Phase 2 Components

Run and fix any missing coverage. All new functions should have at minimum a happy-path test and one error/edge test.

```bash
python3 -m pytest tests/unit/ -v --tb=short
```

Target: 55+ tests passing (up from 43).

**Missing tests to add:**
- `test_gmail_history_poller.py` — already created in Task 2
- `test_llm_triage.py` — already created in Task 3
- `test_focus_mode.py` — already created in Task 5
- `test_outlook_auth.py` — already created in Task 6
- `test_outlook_poller.py` — already created in Task 7
- `test_gcal_poller.py` — already created in Task 9
- `test_weekly_review.py` — test `generate_weekly_review` with mock DB

```bash
git add tests/unit/
git commit -m "test: unit tests for all phase 2 components"
```

---

## Task 15: Update Worker Scheduler

**Files:**
- Modify: `apps/worker/src/worker/main.py`

Final scheduler after all tasks:

```python
# apps/worker/src/worker/main.py
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from worker.jobs import (
    job_poll_and_normalize,
    job_poll_outlook,
    job_poll_gcal,
    job_extract_pending,
    job_schedule_reminders,
    job_daily_pvi_and_digest,
    job_meeting_prep,
)
from core.config import get_settings
import structlog

log = structlog.get_logger()


def start():
    settings = get_settings()
    scheduler = BlockingScheduler()

    scheduler.add_job(job_poll_and_normalize, IntervalTrigger(minutes=2), id="poll_gmail")
    scheduler.add_job(job_poll_outlook, IntervalTrigger(minutes=2), id="poll_outlook")
    scheduler.add_job(job_poll_gcal, IntervalTrigger(minutes=15), id="poll_gcal")
    scheduler.add_job(job_extract_pending, IntervalTrigger(minutes=5), id="extract_pending")
    scheduler.add_job(job_schedule_reminders, IntervalTrigger(minutes=1), id="dispatch_reminders")
    scheduler.add_job(job_meeting_prep, IntervalTrigger(minutes=5), id="meeting_prep")
    scheduler.add_job(job_daily_pvi_and_digest, CronTrigger(hour=7, minute=0), id="daily_pvi_digest")

    log.info("scheduler_starting", jobs=scheduler.get_jobs())
    scheduler.start()


if __name__ == "__main__":
    start()
```

```bash
git add apps/worker/src/worker/main.py
git commit -m "feat: worker scheduler updated with all phase 2 jobs"
```

---

## Testing Each Feature

| Feature | Test command |
|---|---|
| DB migration | `cd infra && python3 -m alembic upgrade head` |
| Gmail History API | `claw sync` twice — second should be near-instant |
| LLM triage | `LLM_LABEL_FILTER=[] claw sync` — watch for `extraction_skipped_triage` |
| claw today | `claw today` |
| Focus mode | `claw focus start 5m && claw focus status && claw focus end` |
| Outlook auth | `claw connect outlook` — opens device code flow |
| Outlook poll | `claw sync` — watch for `outlook_message_inserted` |
| Google Calendar | `claw connect gcal && claw sync && claw today` (events appear) |
| TUI dashboard | `claw dash` — q to quit |
| Weekly review | `claw digest --weekly` |
| Reply drafts | `claw reply list` |
| Worker | `claw worker start` — all 7 jobs listed in startup banner |
