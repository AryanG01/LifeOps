"""
Normalizer: converts raw_events into canonical messages with dedup.
Idempotent: rerunning does not create duplicate messages (enforced by DB unique constraint).
"""
import hashlib
from datetime import datetime, timezone

import structlog

from connectors.canvas.parser import parse_canvas_email
from core.db.engine import get_db
from core.db.models import Message, RawEvent

log = structlog.get_logger()


def compute_dedup_hash(user_id: str, external_id: str, sender: str, subject: str) -> str:
    """Stable SHA-256 hash for deduplication. Public for testability."""
    key = f"{user_id}:{external_id}:{sender}:{subject}"
    return hashlib.sha256(key.encode()).hexdigest()


def _parse_gmail_date(internal_date_ms: str | None) -> datetime:
    """Convert Gmail internalDate (epoch ms string) to timezone-aware datetime."""
    if internal_date_ms:
        try:
            ts = int(internal_date_ms) / 1000
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (ValueError, OverflowError):
            pass
    return datetime.now(tz=timezone.utc)


def _parse_outlook_date(received_at: str | None) -> datetime:
    """Convert Graph API receivedDateTime ISO string to timezone-aware datetime."""
    if received_at:
        try:
            return datetime.fromisoformat(received_at.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(tz=timezone.utc)


def _extract_fields_from_payload(payload: dict, event_external_id: str | None) -> dict:
    """Detect source format (Gmail vs Outlook) and return normalised fields dict."""
    if "gmail_id" in payload:
        # Gmail format
        return {
            "sender": payload.get("sender", ""),
            "subject": payload.get("subject", ""),
            "body": payload.get("body_text", payload.get("snippet", "")),
            "external_id": payload.get("gmail_id", event_external_id or ""),
            "message_ts": _parse_gmail_date(payload.get("internal_date")),
            "label_ids": payload.get("label_ids", []),
        }
    else:
        # Outlook / Graph format
        return {
            "sender": payload.get("sender", ""),
            "subject": payload.get("title", ""),
            "body": payload.get("body_full", payload.get("body_preview", "")),
            "external_id": payload.get("external_id", event_external_id or ""),
            "message_ts": _parse_outlook_date(payload.get("received_at")),
            "label_ids": [],
        }


def normalize_raw_event(raw_event_id: str) -> str | None:
    """
    Normalize one raw_event into a message.
    Returns the new message_id on insert, None if skipped (duplicate or error).
    Marks raw_event.processed_at on success or duplicate.
    """
    with get_db() as db:
        event = db.query(RawEvent).filter_by(id=raw_event_id).first()
        if not event:
            log.error("raw_event_not_found", raw_event_id=raw_event_id)
            return None
        if event.processed_at is not None:
            log.debug("raw_event_already_processed", raw_event_id=raw_event_id)
            return None

        payload: dict = event.payload_json
        fields = _extract_fields_from_payload(payload, event.external_id)
        sender: str = fields["sender"]
        subject: str = fields["subject"]
        body: str = fields["body"]
        external_id: str = fields["external_id"]
        message_ts: datetime = fields["message_ts"]

        dedup_hash = compute_dedup_hash(str(event.user_id), external_id, sender, subject)

        canvas = parse_canvas_email(sender, subject, body)
        extra: dict = {"label_ids": fields["label_ids"]}
        if canvas.is_canvas:
            extra.update({
                "canvas_type": canvas.canvas_type,
                "course_code": canvas.course_code,
                "assignment_title": canvas.assignment_title,
                "due_at_raw": canvas.due_at_raw,
                "canvas_url": canvas.canvas_url,
            })

        msg = Message(
            user_id=str(event.user_id),
            source_id=str(event.source_id),
            raw_event_id=str(event.id),
            external_id=external_id,
            sender=sender,
            title=subject or "(no subject)",
            body_preview=body[:500],
            body_full=body if len(body) > 500 else None,
            message_ts=message_ts,
            dedup_hash=dedup_hash,
            is_canvas=canvas.is_canvas,
            extra_json=extra,
        )

        try:
            db.add(msg)
            db.flush()
            msg_id = str(msg.id)
            event.processed_at = datetime.now(tz=timezone.utc)
            db.commit()
            log.info(
                "message_normalized",
                message_id=msg_id,
                raw_event_id=raw_event_id,
                is_canvas=canvas.is_canvas,
            )
            return msg_id
        except Exception as exc:
            db.rollback()
            error_str = str(exc).lower()
            if "unique" in error_str or "duplicate" in error_str:
                # Already exists — mark raw_event processed
                with get_db() as db2:
                    ev2 = db2.query(RawEvent).filter_by(id=raw_event_id).first()
                    if ev2:
                        ev2.processed_at = datetime.now(tz=timezone.utc)
                        db2.commit()
                log.info("message_deduped", raw_event_id=raw_event_id)
                return None
            # Real error — record it
            with get_db() as db2:
                ev2 = db2.query(RawEvent).filter_by(id=raw_event_id).first()
                if ev2:
                    ev2.processing_error = str(exc)[:500]
                    db2.commit()
            log.error("normalization_failed", raw_event_id=raw_event_id, error=str(exc))
            return None


def normalize_all_pending() -> int:
    """
    Process all unprocessed raw_events without errors.
    Returns count of successfully normalized messages.
    """
    with get_db() as db:
        pending_ids: list[str] = [
            str(row.id)
            for row in db.query(RawEvent.id).filter(
                RawEvent.processed_at.is_(None),
                RawEvent.processing_error.is_(None),
            )
        ]

    count = 0
    for raw_event_id in pending_ids:
        result = normalize_raw_event(raw_event_id)
        if result:
            count += 1
    return count
