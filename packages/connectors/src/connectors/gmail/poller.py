"""Gmail polling connector. Uses messages.list + messages.get with exponential backoff."""
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _with_backoff(fn, max_retries: int = 3):
    """Retry fn with exponential backoff on Gmail quota / rate-limit errors."""
    for attempt in range(max_retries):
        try:
            return fn()
        except HttpError as exc:
            if exc.resp.status in (429, 403) and attempt < max_retries - 1:
                wait = 2 ** attempt
                log.warning(
                    "gmail_quota_backoff",
                    attempt=attempt,
                    wait_seconds=wait,
                    status=exc.resp.status,
                )
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


def _decode_body(payload: dict) -> str:
    """Extract plain-text body from a Gmail message payload."""
    # Direct body
    body_data = payload.get("body", {}).get("data", "")
    if body_data:
        return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")

    # Multipart — find text/plain part
    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/plain":
            data = part.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    return ""


# ---------------------------------------------------------------------------
# Main polling function
# ---------------------------------------------------------------------------

def poll_gmail(user_id: str, source_id: str) -> int:
    """
    Poll Gmail inbox for new messages and store as raw_events.
    Returns count of newly inserted raw_events.
    """
    settings = get_settings()
    service = _build_service()

    # Fetch existing external_ids to avoid re-fetching
    with get_db() as db:
        existing_ids: set[str] = {
            row.external_id
            for row in db.query(RawEvent.external_id)
            .filter(
                RawEvent.user_id == user_id,
                RawEvent.source_id == source_id,
                RawEvent.external_id.isnot(None),
            )
        }

    fmt = "full" if settings.privacy_store_full_bodies else "metadata"

    # List message IDs
    list_result: dict = _with_backoff(lambda: (
        service.users()
        .messages()
        .list(userId="me", labelIds=["INBOX", "UNREAD"], maxResults=settings.gmail_max_results)
        .execute()
    ))

    message_stubs: list[dict] = list_result.get("messages", [])
    inserted = 0

    for stub in message_stubs:
        msg_id: str = stub["id"]
        if msg_id in existing_ids:
            continue

        # Fetch full/metadata message
        msg: dict = _with_backoff(lambda: (  # noqa: B023
            service.users().messages().get(userId="me", id=msg_id, format=fmt).execute()
        ))

        payload = msg.get("payload", {})
        headers = payload.get("headers", [])
        sender = _extract_header(headers, "From")
        subject = _extract_header(headers, "Subject")
        body_text = _decode_body(payload) if settings.privacy_store_full_bodies else ""

        raw_payload = {
            "gmail_id": msg_id,
            "thread_id": msg.get("threadId"),
            "snippet": msg.get("snippet", ""),
            "label_ids": msg.get("labelIds", []),
            "internal_date": msg.get("internalDate"),
            "sender": sender,
            "subject": subject,
            "body_text": body_text[:10_000],  # cap at 10k chars
            "format": fmt,
        }

        with get_db() as db:
            event = RawEvent(
                user_id=user_id,
                source_id=source_id,
                external_id=msg_id,
                payload_json=raw_payload,
            )
            db.add(event)
            try:
                db.commit()
                inserted += 1
                log.info("raw_event_inserted", external_id=msg_id, user_id=user_id)
            except Exception:
                db.rollback()
                # UniqueConstraint violation — already exists

    with get_db() as db:
        source = db.query(Source).filter_by(id=source_id).first()
        if source:
            source.last_synced_at = datetime.now(tz=timezone.utc)
            db.commit()

    log.info("gmail_poll_complete", inserted=inserted, user_id=user_id, source_id=source_id)
    return inserted
