# T9: Web Dashboard — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** A minimal, clean web UI at http://localhost:8000 showing tasks, emails, PVI, and digest.
**Architecture:** FastAPI backend (already exists in apps/api/) + Jinja2 HTML templates + minimal vanilla JS. No React. Single-user, API key auth via header or query param.
**Tech Stack:** FastAPI, Jinja2, HTMX (via CDN), TailwindCSS (via CDN), existing core models
**Test command:** PYTHONPATH=packages/core/src:packages/connectors/src:packages/cli/src python3 -m pytest tests/unit/ -v

---

## Context

The existing API (`apps/api/src/api/main.py`) already registers six routers:

| Prefix | Router file |
|--------|-------------|
| `/v1/sync` | `api/routes/sync.py` |
| `/v1/inbox` | `api/routes/inbox.py` |
| `/v1/tasks` | `api/routes/tasks.py` |
| `/v1/digest` | `api/routes/digest.py` |
| `/v1/pvi` | `api/routes/pvi.py` |
| `/v1/replay` | `api/routes/replay.py` |
| `/health` | inline in `main.py` |

The dashboard adds new routes directly to `main.py` (HTML pages) and new `/api/` convenience
endpoints (JSON, simpler than the versioned `/v1/` routes, used by HTMX partials).

Relevant ORM models:
- `ActionItem` — `id`, `user_id`, `title`, `details`, `due_at`, `priority`, `status`, `created_at`
- `Message` + `MessageSummary` — `sender`, `title`, `body_preview`, `urgency`, `summary_short`
- `PVIDailyScore` — `user_id`, `date`, `score`, `regime`, `explanation`

Settings fields used:
- `default_user_id` — scopes all queries
- `api_host`, `api_port` — for `uvicorn` launch
- `dashboard_api_key` — new field added in Task 1

---

## Tasks

### Task 1 — Add API key auth to FastAPI

**Files modified:**
- `packages/core/src/core/config.py` — add `dashboard_api_key` field
- `apps/api/src/api/auth.py` — new file with `get_api_key` dependency
- `apps/api/src/api/main.py` — import and use `get_api_key` on HTML routes (not on `/health`)

**Step 1a — config.py**

After the existing API server block (around line 37), add:

```python
# Dashboard
dashboard_api_key: str = Field(default="")
```

Map: `DASHBOARD_API_KEY` in `.env`. When empty, auth is disabled (dev convenience).

Add to `.env.example`:
```dotenv
# Web dashboard
DASHBOARD_API_KEY=change_me_in_production
```

**Step 1b — `apps/api/src/api/auth.py`**

```python
# apps/api/src/api/auth.py
from fastapi import Depends, HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader, APIKeyQuery

_header_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)
_query_scheme = APIKeyQuery(name="key", auto_error=False)


def get_api_key(
    header_key: str = Security(_header_scheme),
    query_key: str = Security(_query_scheme),
) -> str:
    from core.config import get_settings
    expected = get_settings().dashboard_api_key
    if not expected:
        return ""  # Auth disabled when key not configured
    provided = header_key or query_key
    if provided != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key",
        )
    return provided
```

**Tests (2) — `tests/unit/test_dashboard_auth.py`**

```python
# tests/unit/test_dashboard_auth.py
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient


def _make_app(api_key="secret"):
    """Return a minimal FastAPI app with get_api_key protecting a test route."""
    from fastapi import FastAPI, Depends
    app = FastAPI()

    def _get_api_key_dep():
        from api.auth import get_api_key
        return Depends(get_api_key)

    @app.get("/protected")
    def protected(key=Depends(__import__("api.auth", fromlist=["get_api_key"]).get_api_key)):
        return {"ok": True}

    return app


def test_valid_api_key_returns_200():
    with patch("core.config.get_settings") as mock_settings:
        mock_settings.return_value.dashboard_api_key = "secret"
        from api.auth import get_api_key
        from fastapi import FastAPI, Depends
        app = FastAPI()

        @app.get("/protected")
        def _p(key=Depends(get_api_key)):
            return {"ok": True}

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/protected", headers={"X-API-Key": "secret"})
        assert resp.status_code == 200


def test_invalid_api_key_returns_403():
    with patch("core.config.get_settings") as mock_settings:
        mock_settings.return_value.dashboard_api_key = "secret"
        from api.auth import get_api_key
        from fastapi import FastAPI, Depends
        app = FastAPI()

        @app.get("/protected")
        def _p(key=Depends(get_api_key)):
            return {"ok": True}

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/protected", headers={"X-API-Key": "wrong"})
        assert resp.status_code == 403
```

Run: `PYTHONPATH=packages/core/src:packages/connectors/src:packages/cli/src:apps/api/src python3 -m pytest tests/unit/test_dashboard_auth.py -v`

---

### Task 2 — Add REST JSON endpoints to `apps/api/src/api/main.py`

These `/api/` endpoints are distinct from the existing `/v1/` router endpoints. They are simpler,
dashboard-facing, and do not require the full router structure.

Add directly to `apps/api/src/api/main.py` (or to a new `api/routes/dashboard.py` router and
include it with prefix `/api`).

**Recommended approach:** New router file `apps/api/src/api/routes/dashboard_api.py`:

```python
# apps/api/src/api/routes/dashboard_api.py
from fastapi import APIRouter, Depends
from typing import Any
from api.auth import get_api_key

router = APIRouter(dependencies=[Depends(get_api_key)])


@router.get("/tasks")
def get_tasks() -> list[dict[str, Any]]:
    """Open ActionItems for default_user_id."""
    from core.config import get_settings
    from core.db.engine import get_db
    from core.db.models import ActionItem
    settings = get_settings()
    with get_db() as db:
        items = (
            db.query(ActionItem)
            .filter(
                ActionItem.user_id == settings.default_user_id,
                ActionItem.status == "proposed",
            )
            .order_by(ActionItem.priority.desc(), ActionItem.created_at.desc())
            .limit(50)
            .all()
        )
        return [
            {
                "id": str(i.id),
                "title": i.title,
                "details": i.details,
                "due_at": i.due_at.isoformat() if i.due_at else None,
                "priority": i.priority,
                "status": i.status,
            }
            for i in items
        ]


@router.get("/messages")
def get_messages() -> list[dict[str, Any]]:
    """Last 20 messages with their short summary (if available)."""
    from core.config import get_settings
    from core.db.engine import get_db
    from core.db.models import Message, MessageSummary
    settings = get_settings()
    with get_db() as db:
        msgs = (
            db.query(Message)
            .filter(Message.user_id == settings.default_user_id)
            .order_by(Message.message_ts.desc())
            .limit(20)
            .all()
        )
        result = []
        for m in msgs:
            summary = (
                db.query(MessageSummary)
                .filter(MessageSummary.message_id == m.id)
                .order_by(MessageSummary.extracted_at.desc())
                .first()
            )
            result.append({
                "id": str(m.id),
                "sender": m.sender,
                "title": m.title,
                "body_preview": m.body_preview,
                "message_ts": m.message_ts.isoformat(),
                "summary_short": summary.summary_short if summary else None,
                "urgency": summary.urgency if summary else None,
            })
        return result


@router.get("/pvi/today")
def get_pvi_today() -> dict[str, Any]:
    """Today's PVI score for default_user_id."""
    from core.config import get_settings
    from core.db.engine import get_db
    from core.db.models import PVIDailyScore
    from datetime import date
    settings = get_settings()
    with get_db() as db:
        row = (
            db.query(PVIDailyScore)
            .filter(
                PVIDailyScore.user_id == settings.default_user_id,
                PVIDailyScore.date == date.today(),
            )
            .first()
        )
        if not row:
            return {"score": None, "regime": None, "explanation": None}
        return {
            "score": row.score,
            "regime": row.regime,
            "explanation": row.explanation,
            "date": row.date.isoformat(),
        }
```

Register in `apps/api/src/api/main.py`:

```python
from api.routes import dashboard_api
app.include_router(dashboard_api.router, prefix="/api")
```

**Tests (3) — `tests/unit/test_dashboard_api.py`**

```python
# tests/unit/test_dashboard_api.py
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


def _make_client():
    with patch("core.config.get_settings") as mock_settings:
        mock_settings.return_value.dashboard_api_key = ""  # auth disabled
        mock_settings.return_value.default_user_id = "uid-1"
        from api.main import app
        return TestClient(app)


def test_get_tasks_returns_list():
    mock_item = MagicMock()
    mock_item.id = "task-uuid-1"
    mock_item.title = "Reply to Prof Chen"
    mock_item.details = ""
    mock_item.due_at = None
    mock_item.priority = 75
    mock_item.status = "proposed"

    mock_db = MagicMock()
    mock_db.__enter__ = lambda s: mock_db
    mock_db.__exit__ = MagicMock(return_value=False)
    mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [mock_item]

    with patch("core.db.engine.get_db", return_value=mock_db), \
         patch("core.config.get_settings") as ms:
        ms.return_value.dashboard_api_key = ""
        ms.return_value.default_user_id = "uid-1"
        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        resp = client.get("/api/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["title"] == "Reply to Prof Chen"


def test_get_messages_returns_list():
    mock_msg = MagicMock()
    mock_msg.id = "msg-uuid-1"
    mock_msg.sender = "alice@example.com"
    mock_msg.title = "Homework due"
    mock_msg.body_preview = "Please submit..."
    mock_msg.message_ts = __import__("datetime").datetime(2026, 3, 3, 9, 0)

    mock_db = MagicMock()
    mock_db.__enter__ = lambda s: mock_db
    mock_db.__exit__ = MagicMock(return_value=False)
    # First query call returns messages; second (MessageSummary) returns None
    mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [mock_msg]
    mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

    with patch("core.db.engine.get_db", return_value=mock_db), \
         patch("core.config.get_settings") as ms:
        ms.return_value.dashboard_api_key = ""
        ms.return_value.default_user_id = "uid-1"
        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        resp = client.get("/api/messages")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


def test_get_pvi_today_no_score():
    mock_db = MagicMock()
    mock_db.__enter__ = lambda s: mock_db
    mock_db.__exit__ = MagicMock(return_value=False)
    mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = None

    with patch("core.db.engine.get_db", return_value=mock_db), \
         patch("core.config.get_settings") as ms:
        ms.return_value.dashboard_api_key = ""
        ms.return_value.default_user_id = "uid-1"
        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        resp = client.get("/api/pvi/today")
        assert resp.status_code == 200
        assert resp.json()["score"] is None
```

---

### Task 3 — Add Jinja2 templates and dashboard HTML

**Dependencies to add to `apps/api/pyproject.toml` (or `requirements.txt`):**

```
jinja2>=3.1
```

HTMX and TailwindCSS are loaded via CDN — no npm required.

**Step 3a — Install Jinja2 in the API app**

In `apps/api/src/api/main.py`, add:

```python
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request, Depends
from pathlib import Path

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
```

**Step 3b — `apps/api/src/api/templates/base.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Clawdbot {% block title %}{% endblock %}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://unpkg.com/htmx.org@1.9.12"></script>
</head>
<body class="bg-gray-950 text-gray-100 min-h-screen font-mono">
  <nav class="flex items-center gap-6 px-8 py-4 bg-gray-900 border-b border-gray-800">
    <span class="text-indigo-400 font-bold text-lg">Clawdbot</span>
    <a href="/" class="hover:text-indigo-300">Dashboard</a>
    <a href="/tasks" class="hover:text-indigo-300">Tasks</a>
    <a href="/inbox" class="hover:text-indigo-300">Inbox</a>
  </nav>
  <main class="px-8 py-6">
    {% block content %}{% endblock %}
  </main>
</body>
</html>
```

**Step 3c — `apps/api/src/api/templates/dashboard.html`**

```html
{% extends "base.html" %}
{% block title %}Dashboard{% endblock %}
{% block content %}
<h1 class="text-2xl font-bold mb-6">Today — {{ today }}</h1>

<!-- PVI Score -->
<section class="mb-8">
  <h2 class="text-lg font-semibold text-indigo-400 mb-2">PVI Score</h2>
  <div id="pvi-block"
       hx-get="/api/pvi/today"
       hx-trigger="load"
       hx-swap="innerHTML">
    <span class="text-gray-500">Loading...</span>
  </div>
</section>

<!-- Open Tasks -->
<section class="mb-8">
  <h2 class="text-lg font-semibold text-indigo-400 mb-2">Open Tasks</h2>
  <div id="tasks-summary"
       hx-get="/api/tasks"
       hx-trigger="load"
       hx-swap="innerHTML">
    <span class="text-gray-500">Loading...</span>
  </div>
</section>

<!-- Recent Emails -->
<section>
  <h2 class="text-lg font-semibold text-indigo-400 mb-2">Recent Emails</h2>
  <div id="inbox-summary"
       hx-get="/api/messages"
       hx-trigger="load"
       hx-swap="innerHTML">
    <span class="text-gray-500">Loading...</span>
  </div>
</section>
{% endblock %}
```

**Step 3d — `GET /` route in `apps/api/src/api/main.py`**

```python
from fastapi import Request
from datetime import date as _date

@app.get("/", include_in_schema=False)
def dashboard_home(
    request: Request,
    _key=Depends(get_api_key),
):
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "today": _date.today().strftime("%A, %B %d %Y")},
    )
```

No unit tests for templates — verified by running:
```
cd /Users/aryanganju/Desktop/Code/LifeOps
PYTHONPATH=packages/core/src:apps/api/src uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```
Then open `http://127.0.0.1:8000/` in a browser.

---

### Task 4 — Add `/tasks` and `/inbox` pages with HTMX actions

**New template files:**
- `apps/api/src/api/templates/tasks.html`
- `apps/api/src/api/templates/inbox.html`

**`tasks.html`**

```html
{% extends "base.html" %}
{% block title %}Tasks{% endblock %}
{% block content %}
<h1 class="text-2xl font-bold mb-6">Open Tasks</h1>
<div id="tasks-list"
     hx-get="/api/tasks"
     hx-trigger="load"
     hx-swap="innerHTML">
  <span class="text-gray-500">Loading...</span>
</div>
{% endblock %}
```

HTMX partial for task rows (returned by `/tasks/{id}/accept` and `/tasks/{id}/dismiss`):

```html
<!-- Partial: single task row (no extends, used as HTMX swap target) -->
<tr id="task-{{ task.id }}" class="opacity-50 line-through text-gray-500">
  <td colspan="4">{{ task.title }} — {{ action }}</td>
</tr>
```

**New routes in `apps/api/src/api/routes/dashboard_api.py`**

```python
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

# Accept task
@router.post("/tasks/{task_id}/accept", response_class=HTMLResponse)
def accept_task(task_id: str) -> str:
    from core.db.engine import get_db
    from core.db.models import ActionItem
    from datetime import datetime, timezone
    with get_db() as db:
        item = db.query(ActionItem).filter(ActionItem.id == task_id).first()
        if item:
            item.status = "accepted"
            item.updated_at = datetime.now(timezone.utc)
            db.commit()
    return f'<tr id="task-{task_id}" class="opacity-40 text-gray-500"><td colspan="4">Accepted</td></tr>'


# Dismiss task
@router.post("/tasks/{task_id}/dismiss", response_class=HTMLResponse)
def dismiss_task(task_id: str) -> str:
    from core.db.engine import get_db
    from core.db.models import ActionItem
    from datetime import datetime, timezone
    with get_db() as db:
        item = db.query(ActionItem).filter(ActionItem.id == task_id).first()
        if item:
            item.status = "dismissed"
            item.updated_at = datetime.now(timezone.utc)
            db.commit()
    return f'<tr id="task-{task_id}" class="opacity-40 text-gray-500"><td colspan="4">Dismissed</td></tr>'
```

**`GET /tasks` and `GET /inbox` page routes in `main.py`**

```python
@app.get("/tasks", include_in_schema=False)
def tasks_page(request: Request, _key=Depends(get_api_key)):
    return templates.TemplateResponse("tasks.html", {"request": request})


@app.get("/inbox", include_in_schema=False)
def inbox_page(request: Request, _key=Depends(get_api_key)):
    return templates.TemplateResponse("inbox.html", {"request": request})
```

**Tests (2) — `tests/unit/test_dashboard_htmx.py`**

```python
# tests/unit/test_dashboard_htmx.py
from unittest.mock import MagicMock, patch


def _mock_db_with_item(item):
    mock_db = MagicMock()
    mock_db.__enter__ = lambda s: mock_db
    mock_db.__exit__ = MagicMock(return_value=False)
    mock_db.query.return_value.filter.return_value.first.return_value = item
    return mock_db


def test_accept_task_sets_status():
    mock_item = MagicMock()
    mock_item.status = "proposed"
    mock_db = _mock_db_with_item(mock_item)

    with patch("core.db.engine.get_db", return_value=mock_db), \
         patch("core.config.get_settings") as ms:
        ms.return_value.dashboard_api_key = ""
        ms.return_value.default_user_id = "uid-1"
        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        resp = client.post("/api/tasks/task-uuid-1/accept")
        assert resp.status_code == 200
        assert mock_item.status == "accepted"
        mock_db.commit.assert_called_once()


def test_dismiss_task_sets_status():
    mock_item = MagicMock()
    mock_item.status = "proposed"
    mock_db = _mock_db_with_item(mock_item)

    with patch("core.db.engine.get_db", return_value=mock_db), \
         patch("core.config.get_settings") as ms:
        ms.return_value.dashboard_api_key = ""
        ms.return_value.default_user_id = "uid-1"
        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        resp = client.post("/api/tasks/task-uuid-1/dismiss")
        assert resp.status_code == 200
        assert mock_item.status == "dismissed"
        mock_db.commit.assert_called_once()
```

---

### Task 5 — Verify `apps/api/Dockerfile` includes templates

**File:** `apps/api/Dockerfile`

Check that the `COPY` step that copies `apps/api/` also captures the `templates/` subdirectory.
A typical Dockerfile for this project already does `COPY . .` or `COPY apps/api/ apps/api/`, so
the templates directory is included automatically.

Action: open `apps/api/Dockerfile`, confirm no explicit exclusion of `templates/` or `*.html`
in `.dockerignore`. If a `.dockerignore` entry excludes HTML files, remove it.

If the Dockerfile does not exist yet, create a minimal one:

```dockerfile
# apps/api/Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -e apps/api -e packages/core -e packages/connectors
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

No unit test — verified by running `docker build -f apps/api/Dockerfile .` from project root.

---

### Task 6 — Update Phase 3 tracker for T9 done

**File:** `docs/plans/2026-03-02-clawdbot-phase3.md`

Find the T9 line and change `[ ]` to `[x]`. Add a completion note:

```
- [x] T9: Web dashboard — FastAPI + Jinja2 + HTMX, /tasks /inbox /api/* endpoints, API key auth
```

---

## Acceptance Checklist

- [ ] Task 1: `dashboard_api_key` in Settings; `get_api_key` dependency works; 2 auth tests pass
- [ ] Task 2: `/api/tasks`, `/api/messages`, `/api/pvi/today` return correct JSON; 3 tests pass
- [ ] Task 3: `base.html` + `dashboard.html` templates exist; `GET /` renders dashboard
- [ ] Task 4: `tasks.html` + `inbox.html` exist; `/tasks/{id}/accept` + `/dismiss` update DB; 2 HTMX tests pass
- [ ] Task 5: `apps/api/Dockerfile` confirmed to include templates directory
- [ ] Task 6: Phase 3 tracker updated
- [ ] All 109 unit tests pass (102 existing + 2 auth + 3 api + 2 htmx)

## Files Modified / Created

| Action | Path |
|--------|------|
| Modified | `packages/core/src/core/config.py` |
| Created  | `apps/api/src/api/auth.py` |
| Modified | `apps/api/src/api/main.py` |
| Created  | `apps/api/src/api/routes/dashboard_api.py` |
| Created  | `apps/api/src/api/templates/base.html` |
| Created  | `apps/api/src/api/templates/dashboard.html` |
| Created  | `apps/api/src/api/templates/tasks.html` |
| Created  | `apps/api/src/api/templates/inbox.html` |
| Modified | `apps/api/Dockerfile` (verify only) |
| Modified | `.env.example` |
| Modified | `docs/plans/2026-03-02-clawdbot-phase3.md` |
| Created  | `tests/unit/test_dashboard_auth.py` |
| Created  | `tests/unit/test_dashboard_api.py` |
| Created  | `tests/unit/test_dashboard_htmx.py` |
