from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Label(BaseModel):
    model_config = {"extra": "forbid"}

    label: str
    confidence: float = Field(ge=0.0, le=1.0)


class ActionItemSchema(BaseModel):
    model_config = {"extra": "forbid"}

    title: str
    details: str
    due_at: Optional[datetime] = None
    priority: int = Field(ge=0, le=100)
    confidence: float = Field(ge=0.0, le=1.0)


class ReplyDraftSchema(BaseModel):
    model_config = {"extra": "forbid"}

    tone: str
    draft_text: str


class Evidence(BaseModel):
    model_config = {"extra": "forbid"}

    due_date_evidence: Optional[str] = None
    source_url: Optional[str] = None


class ExtractionResult(BaseModel):
    model_config = {"extra": "forbid"}

    labels: list[Label]
    summary_short: str
    summary_long: Optional[str] = None
    action_items: list[ActionItemSchema]
    reply_drafts: list[ReplyDraftSchema] = Field(default_factory=list)
    urgency: float = Field(ge=0.0, le=1.0)
    evidence: Optional[Evidence] = None
