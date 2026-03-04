# apps/api/src/api/routes/dashboard_api.py
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
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
    return f'<tr id="task-{task_id}" class="opacity-40 text-gray-500"><td colspan="4">Accepted</td></tr>'


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
    return f'<tr id="task-{task_id}" class="opacity-40 text-gray-500"><td colspan="4">Dismissed</td></tr>'
