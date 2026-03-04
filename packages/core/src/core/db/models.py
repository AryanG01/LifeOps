import uuid
from datetime import datetime, date, timezone
from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float,
    ForeignKey, Integer, JSON, String, Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    email = Column(Text, nullable=False, unique=True)
    display_name = Column(Text)
    timezone = Column(Text, nullable=False, default="Asia/Singapore")
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=timezone.utc))


class Source(Base):
    __tablename__ = "sources"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    source_type = Column(Text, nullable=False)
    display_name = Column(Text, nullable=False)
    config_json = Column(JSON, nullable=False, default=dict)
    last_synced_at = Column(DateTime(timezone=True))
    sync_cursor = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=timezone.utc))

    __table_args__ = (UniqueConstraint("user_id", "source_type", "display_name"),)


class RawEvent(Base):
    __tablename__ = "raw_events"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    source_id = Column(UUID(as_uuid=False), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    external_id = Column(Text)
    payload_json = Column(JSON, nullable=False)
    received_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=timezone.utc))
    processed_at = Column(DateTime(timezone=True))
    processing_error = Column(Text)

    __table_args__ = (UniqueConstraint("user_id", "source_id", "external_id"),)


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    source_id = Column(UUID(as_uuid=False), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    raw_event_id = Column(UUID(as_uuid=False), ForeignKey("raw_events.id"))
    external_id = Column(Text)
    sender = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    body_preview = Column(Text, nullable=False, default="")
    body_full = Column(Text)
    message_ts = Column(DateTime(timezone=True), nullable=False)
    ingested_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=timezone.utc))
    dedup_hash = Column(Text, nullable=False)
    is_canvas = Column(Boolean, nullable=False, default=False)
    extra_json = Column(JSON, nullable=False, default=dict)

    __table_args__ = (UniqueConstraint("user_id", "dedup_hash"),)


class MessageSummary(Base):
    __tablename__ = "message_summaries"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    message_id = Column(UUID(as_uuid=False), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    prompt_version = Column(Text, nullable=False, default="v1")
    summary_short = Column(Text, nullable=False)
    summary_long = Column(Text)
    urgency = Column(Float, nullable=False, default=0.5)
    extraction_failed = Column(Boolean, nullable=False, default=False)
    extracted_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=timezone.utc))

    __table_args__ = (UniqueConstraint("message_id", "prompt_version"),)


class MessageLabel(Base):
    __tablename__ = "message_labels"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    message_id = Column(UUID(as_uuid=False), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    prompt_version = Column(Text, nullable=False, default="v1")
    label = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False)

    __table_args__ = (UniqueConstraint("message_id", "prompt_version", "label"),)


class ReplyDraft(Base):
    __tablename__ = "reply_drafts"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    message_id = Column(UUID(as_uuid=False), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    prompt_version = Column(Text, nullable=False, default="v1")
    tone = Column(Text, nullable=False)
    draft_text = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="proposed")
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=timezone.utc))


class LLMRun(Base):
    __tablename__ = "llm_runs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    message_id = Column(UUID(as_uuid=False), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    prompt_version = Column(Text, nullable=False)
    model = Column(Text, nullable=False)
    input_tokens = Column(Integer)
    output_tokens = Column(Integer)
    latency_ms = Column(Integer)
    validation_passed = Column(Boolean, nullable=False)
    validation_error = Column(Text)
    attempt = Column(Integer, nullable=False, default=1)
    ran_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=timezone.utc))


class ActionItem(Base):
    __tablename__ = "action_items"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    message_id = Column(UUID(as_uuid=False), ForeignKey("messages.id"))
    title = Column(Text, nullable=False)
    details = Column(Text, nullable=False, default="")
    due_at = Column(DateTime(timezone=True))
    priority = Column(Integer, nullable=False, default=50)
    confidence = Column(Float, nullable=False, default=0.5)
    status = Column(Text, nullable=False, default="proposed")
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=timezone.utc))


class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    action_item_id = Column(UUID(as_uuid=False), ForeignKey("action_items.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    remind_at = Column(DateTime(timezone=True), nullable=False)
    channel = Column(Text, nullable=False, default="cli")
    status = Column(Text, nullable=False, default="pending")
    sent_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=timezone.utc))

    __table_args__ = (UniqueConstraint("action_item_id", "remind_at", "channel"),)


class PVIDailyFeature(Base):
    __tablename__ = "pvi_daily_features"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False)
    tasks_open = Column(Integer, nullable=False, default=0)
    tasks_overdue = Column(Integer, nullable=False, default=0)
    inbox_unread = Column(Integer, nullable=False, default=0)
    incoming_24h = Column(Integer, nullable=False, default=0)
    calendar_minutes = Column(Integer, nullable=False, default=0)
    computed_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=timezone.utc))

    __table_args__ = (UniqueConstraint("user_id", "date"),)


class PVIDailyScore(Base):
    __tablename__ = "pvi_daily_scores"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False)
    score = Column(Integer, nullable=False)
    regime = Column(Text, nullable=False)
    explanation = Column(Text, nullable=False)
    computed_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=timezone.utc))

    __table_args__ = (UniqueConstraint("user_id", "date"),)


class Policy(Base):
    __tablename__ = "policies"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False)
    regime = Column(Text, nullable=False)
    max_digest_items = Column(Integer, nullable=False, default=15)
    escalation_level = Column(Text, nullable=False, default="standard")
    reminder_cadence = Column(Text, nullable=False, default="standard")
    auto_activate = Column(Boolean, nullable=False, default=False)
    computed_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=timezone.utc))

    __table_args__ = (UniqueConstraint("user_id", "date"),)


class Digest(Base):
    __tablename__ = "digests"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False)
    content_md = Column(Text, nullable=False)
    regime = Column(Text, nullable=False, default="normal")
    generated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=timezone.utc))

    __table_args__ = (UniqueConstraint("user_id", "date"),)


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
    ingested_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=timezone.utc))

    __table_args__ = (UniqueConstraint("user_id", "external_id"),)


class FocusSession(Base):
    __tablename__ = "focus_sessions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=timezone.utc))
    ends_at = Column(DateTime(timezone=True), nullable=False)
    ended_early_at = Column(DateTime(timezone=True))
    is_active = Column(Boolean, nullable=False, default=True)
