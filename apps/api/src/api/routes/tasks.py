# apps/api/src/api/routes/tasks.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
from core.db.engine import get_db
from core.db.models import ActionItem, Reminder

router = APIRouter()


@router.get("/")
def list_tasks(status: str | None = None,
               user_id: str = "00000000-0000-0000-0000-000000000001"):
    with get_db() as db:
        q = db.query(ActionItem).filter_by(user_id=user_id)
        if status:
            q = q.filter(ActionItem.status == status)
        tasks = q.order_by(ActionItem.due_at).all()
        return [{"id": t.id, "title": t.title, "status": t.status,
                 "due_at": t.due_at, "priority": t.priority} for t in tasks]


def _update_task_status(task_id: str, new_status: str):
    with get_db() as db:
        task = db.query(ActionItem).filter_by(id=task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        task.status = new_status
        task.updated_at = datetime.now(tz=timezone.utc)
        if new_status in ("done", "dismissed"):
            db.query(Reminder).filter_by(
                action_item_id=task_id, status="pending"
            ).update({"status": "cancelled"})
        db.commit()
        return {"id": task_id, "status": new_status}


@router.post("/{task_id}/accept")
def accept_task(task_id: str):
    return _update_task_status(task_id, "active")


@router.post("/{task_id}/done")
def done_task(task_id: str):
    return _update_task_status(task_id, "done")


@router.post("/{task_id}/dismiss")
def dismiss_task(task_id: str):
    return _update_task_status(task_id, "dismissed")


class SnoozeRequest(BaseModel):
    hours: int


@router.post("/{task_id}/snooze")
def snooze_task(task_id: str, req: SnoozeRequest):
    with get_db() as db:
        reminder = db.query(Reminder).filter_by(
            action_item_id=task_id, status="pending"
        ).order_by(Reminder.remind_at).first()
        if not reminder:
            raise HTTPException(status_code=404, detail="No pending reminders")
        reminder.remind_at = reminder.remind_at + timedelta(hours=req.hours)
        reminder.status = "snoozed"
        db.commit()
        return {"snoozed_until": reminder.remind_at}
