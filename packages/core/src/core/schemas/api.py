from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class MessageOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    source_type: str = ""
    sender: str
    title: str
    body_preview: str
    message_ts: datetime
    summary_short: Optional[str] = None
    urgency: Optional[float] = None
    is_canvas: bool
    action_required: bool = False


class TaskOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    title: str
    details: str
    due_at: Optional[datetime] = None
    priority: int
    confidence: float
    status: str
    created_at: datetime


class PVIOut(BaseModel):
    date: date
    score: int
    regime: str
    explanation: str
    features: dict
    policy: dict


class DigestOut(BaseModel):
    date: date
    content_md: str
    regime: str
    generated_at: datetime
