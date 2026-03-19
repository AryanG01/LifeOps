# apps/api/src/api/routes/dashboard_api.py
from fastapi import APIRouter, Depends, Form
from fastapi.responses import HTMLResponse
from typing import Any
from api.auth import get_api_key

router = APIRouter(dependencies=[Depends(get_api_key)])


# ─── Tasks ──────────────────────────────────────────────────────────────────

@router.get("/tasks")
def get_tasks() -> list[dict[str, Any]]:
    """Open ActionItems (proposed + active) for default_user_id."""
    from core.config import get_settings
    from core.db.engine import get_db
    from core.db.models import ActionItem
    from datetime import datetime, timezone
    settings = get_settings()
    now = datetime.now(timezone.utc)
    with get_db() as db:
        items = (
            db.query(ActionItem)
            .filter(
                ActionItem.user_id == settings.default_user_id,
                ActionItem.status.in_(["proposed", "active"]),
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
                "overdue": bool(i.due_at and i.due_at < now),
            }
            for i in items
        ]


@router.post("/tasks/{task_id}/accept", response_class=HTMLResponse)
def accept_task(task_id: str) -> str:
    from core.db.engine import get_db
    from core.db.models import ActionItem
    from datetime import datetime, timezone
    with get_db() as db:
        item = db.query(ActionItem).filter(ActionItem.id == task_id).first()
        if item:
            item.status = "active"
            item.updated_at = datetime.now(timezone.utc)
    return f'<tr id="task-{task_id}" class="opacity-40 text-gray-500"><td colspan="5">✓ Accepted</td></tr>'


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
    return f'<tr id="task-{task_id}" class="opacity-40 text-gray-500"><td colspan="5">✗ Dismissed</td></tr>'


# ─── Messages / Inbox ────────────────────────────────────────────────────────

@router.get("/messages")
def get_messages() -> list[dict[str, Any]]:
    """Last 20 messages with summary and source tag."""
    from core.config import get_settings
    from core.db.engine import get_db
    from core.db.models import Message, MessageSummary, Source
    settings = get_settings()
    with get_db() as db:
        rows = (
            db.query(Message, MessageSummary, Source)
            .outerjoin(MessageSummary, MessageSummary.message_id == Message.id)
            .outerjoin(Source, Source.id == Message.source_id)
            .filter(Message.user_id == settings.default_user_id)
            .order_by(Message.message_ts.desc())
            .limit(20)
            .all()
        )
        return [
            {
                "id": str(m.id),
                "sender": m.sender,
                "title": m.title,
                "body_preview": m.body_preview,
                "message_ts": m.message_ts.isoformat(),
                "summary_short": s.summary_short if s else None,
                "urgency": s.urgency if s else None,
                "source": src.display_name if src else None,
            }
            for m, s, src in rows
        ]


# ─── PVI ────────────────────────────────────────────────────────────────────

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


# ─── Replies ─────────────────────────────────────────────────────────────────

@router.get("/replies")
def get_replies() -> list[dict[str, Any]]:
    """Pending reply drafts for default_user_id (joined via Message)."""
    from core.config import get_settings
    from core.db.engine import get_db
    from core.db.models import ReplyDraft, Message
    settings = get_settings()
    with get_db() as db:
        rows = (
            db.query(ReplyDraft, Message)
            .join(Message, Message.id == ReplyDraft.message_id)
            .filter(
                Message.user_id == settings.default_user_id,
                ReplyDraft.status == "proposed",
            )
            .order_by(ReplyDraft.created_at.desc())
            .limit(20)
            .all()
        )
        return [
            {
                "id": str(d.id),
                "draft_text": d.draft_text,
                "tone": d.tone,
                "sender": m.sender,
                "subject": m.title,
                "message_id": str(m.id),
                "created_at": d.created_at.isoformat(),
            }
            for d, m in rows
        ]


@router.post("/replies/{draft_id}/send", response_class=HTMLResponse)
def send_reply(draft_id: str) -> str:
    from core.db.engine import get_db
    from core.db.models import ReplyDraft, Message
    import base64, email.mime.text
    try:
        with get_db() as db:
            draft = db.query(ReplyDraft).filter(ReplyDraft.id == draft_id).first()
            if not draft:
                return f'<div id="reply-{draft_id}" class="text-red-400">Draft not found.</div>'
            draft_text = draft.draft_text
            message_id = str(draft.message_id)

        with get_db() as db:
            msg = db.query(Message).filter(Message.id == message_id).first()
            if not msg:
                return f'<div id="reply-{draft_id}" class="text-red-400">Message not found.</div>'
            to, subject, thread_id = msg.sender, msg.title, msg.external_id

        from connectors.gmail.auth import get_credentials
        from googleapiclient.discovery import build
        creds = get_credentials()
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        mime = email.mime.text.MIMEText(draft_text)
        mime["To"] = to
        mime["Subject"] = f"Re: {subject}" if not subject.startswith("Re:") else subject
        if thread_id:
            mime["In-Reply-To"] = thread_id
            mime["References"] = thread_id
        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw, "threadId": thread_id}).execute()

        with get_db() as db:
            d = db.query(ReplyDraft).filter(ReplyDraft.id == draft_id).first()
            if d:
                d.status = "sent"

        return f'<div id="reply-{draft_id}" class="text-green-400 py-3">✓ Reply sent.</div>'
    except Exception as exc:
        return f'<div id="reply-{draft_id}" class="text-red-400">Failed: {str(exc)[:80]}</div>'


@router.post("/replies/{draft_id}/dismiss", response_class=HTMLResponse)
def dismiss_reply(draft_id: str) -> str:
    from core.db.engine import get_db
    from core.db.models import ReplyDraft
    with get_db() as db:
        d = db.query(ReplyDraft).filter(ReplyDraft.id == draft_id).first()
        if d:
            d.status = "dismissed"
    return f'<div id="reply-{draft_id}" class="text-gray-500 py-3">✗ Skipped.</div>'


@router.post("/replies/{draft_id}/update", response_class=HTMLResponse)
def update_reply(draft_id: str, draft_text: str = Form(...)) -> str:
    from core.db.engine import get_db
    from core.db.models import ReplyDraft
    with get_db() as db:
        d = db.query(ReplyDraft).filter(ReplyDraft.id == draft_id).first()
        if not d:
            return f'<span class="text-red-400">Draft not found.</span>'
        d.draft_text = draft_text
        updated_text = d.draft_text
    escaped = updated_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'''<div id="draft-text-{draft_id}">
  <p class="text-gray-300 text-sm italic mb-2">{escaped}</p>
  <button onclick="startEdit('{draft_id}', this.parentElement)" class="text-xs text-indigo-400 hover:text-indigo-300">✏️ Edit</button>
</div>'''


# ─── Digest ──────────────────────────────────────────────────────────────────

@router.get("/digest/today")
def get_digest_today() -> dict[str, Any]:
    """Today's digest content. Generates on-demand if not yet stored."""
    from core.config import get_settings
    from core.db.engine import get_db
    from core.db.models import Digest
    from datetime import date
    settings = get_settings()
    today = date.today()
    with get_db() as db:
        row = db.query(Digest).filter(
            Digest.user_id == settings.default_user_id,
            Digest.date == today,
        ).first()
        if row:
            return {"date": today.isoformat(), "content": row.content_md, "regime": row.regime}

    # Generate on-demand
    from core.digest.generator import generate_digest
    content = generate_digest(str(settings.default_user_id))
    return {"date": today.isoformat(), "content": content, "regime": None}


@router.get("/digest/weekly")
def get_digest_weekly() -> dict[str, Any]:
    """Weekly review digest."""
    from core.config import get_settings
    from core.digest.weekly import generate_weekly_review
    settings = get_settings()
    content = generate_weekly_review(str(settings.default_user_id))
    return {"content": content}


@router.post("/digest/generate")
def generate_digest_now() -> dict[str, Any]:
    """Regenerate today's digest."""
    from core.config import get_settings
    from core.digest.generator import generate_digest
    settings = get_settings()
    from core.pvi.engine import compute_pvi_daily
    compute_pvi_daily(str(settings.default_user_id))
    content = generate_digest(str(settings.default_user_id))
    return {"content": content}


# ─── Focus ───────────────────────────────────────────────────────────────────

@router.get("/focus/status")
def get_focus_status() -> dict[str, Any]:
    """Current focus session status."""
    from core.config import get_settings
    from core.db.engine import get_db
    from core.db.models import FocusSession
    from datetime import datetime, timezone
    settings = get_settings()
    now = datetime.now(timezone.utc)
    with get_db() as db:
        session = db.query(FocusSession).filter(
            FocusSession.user_id == settings.default_user_id,
            FocusSession.is_active == True,
        ).first()
        if not session:
            return {"active": False}
        remaining_s = max(0, int((session.ends_at - now).total_seconds()))
        return {
            "active": True,
            "ends_at": session.ends_at.isoformat(),
            "remaining_minutes": remaining_s // 60,
            "remaining_seconds": remaining_s % 60,
        }


@router.post("/focus/start", response_class=HTMLResponse)
def start_focus(minutes: int = Form(default=25)) -> str:
    from core.config import get_settings
    from core.db.engine import get_db
    from core.db.models import FocusSession
    from datetime import datetime, timezone, timedelta
    settings = get_settings()
    now = datetime.now(timezone.utc)
    ends_at = now + timedelta(minutes=max(1, min(minutes, 480)))
    with get_db() as db:
        active = db.query(FocusSession).filter(
            FocusSession.user_id == settings.default_user_id,
            FocusSession.is_active == True,
        ).first()
        if active:
            active.is_active = False
            active.ended_early_at = now
        db.add(FocusSession(
            user_id=settings.default_user_id,
            started_at=now,
            ends_at=ends_at,
            is_active=True,
        ))
    return _focus_html(True, minutes, 0)


@router.post("/focus/end", response_class=HTMLResponse)
def end_focus() -> str:
    from core.config import get_settings
    from core.db.engine import get_db
    from core.db.models import FocusSession
    from datetime import datetime, timezone
    settings = get_settings()
    now = datetime.now(timezone.utc)
    with get_db() as db:
        active = db.query(FocusSession).filter(
            FocusSession.user_id == settings.default_user_id,
            FocusSession.is_active == True,
        ).first()
        if active:
            active.is_active = False
            active.ended_early_at = now
    return _focus_html(False, 0, 0)


def _focus_html(active: bool, remaining_m: int, remaining_s: int) -> str:
    if active:
        return f'''<div id="focus-block" class="flex items-center gap-4">
  <span class="text-green-400 font-semibold">🎯 Focus ON — {remaining_m}m remaining</span>
  <form hx-post="/api/focus/end" hx-target="#focus-block" hx-swap="outerHTML" class="inline">
    <button class="px-3 py-1 bg-red-800 hover:bg-red-700 rounded text-sm">End Focus</button>
  </form>
</div>'''
    return '''<div id="focus-block" class="flex items-center gap-4">
  <span class="text-gray-400">No active focus session</span>
  <form hx-post="/api/focus/start" hx-target="#focus-block" hx-swap="outerHTML" class="inline flex items-center gap-2">
    <input type="number" name="minutes" value="25" min="1" max="480"
           class="w-16 px-2 py-1 bg-gray-800 border border-gray-700 rounded text-sm text-center" />
    <span class="text-gray-500 text-sm">min</span>
    <button class="px-3 py-1 bg-indigo-700 hover:bg-indigo-600 rounded text-sm">Start Focus</button>
  </form>
</div>'''
