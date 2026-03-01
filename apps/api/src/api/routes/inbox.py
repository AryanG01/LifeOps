# apps/api/src/api/routes/inbox.py
from fastapi import APIRouter
from core.db.engine import get_db
from core.db.models import Message, MessageSummary

router = APIRouter()


@router.get("/")
def list_inbox(user_id: str = "00000000-0000-0000-0000-000000000001",
               limit: int = 50, canvas_only: bool = False):
    with get_db() as db:
        q = db.query(Message, MessageSummary).join(
            MessageSummary, MessageSummary.message_id == Message.id, isouter=True
        ).filter(Message.user_id == user_id)
        if canvas_only:
            q = q.filter(Message.is_canvas == True)  # noqa: E712
        q = q.order_by(Message.message_ts.desc()).limit(limit)
        rows = q.all()
        return [
            {
                "id": msg.id,
                "sender": msg.sender,
                "title": msg.title,
                "is_canvas": msg.is_canvas,
                "message_ts": msg.message_ts,
                "summary_short": summary.summary_short if summary else None,
                "urgency": summary.urgency if summary else None,
            }
            for msg, summary in rows
        ]
