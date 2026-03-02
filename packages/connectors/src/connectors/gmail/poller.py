"""Gmail polling connector — uses History API delta for fast incremental sync.

First poll (no cursor): fetches recent messages via messages.list.
Subsequent polls: uses history.list with stored historyId cursor for O(changes) calls.
"""
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


def _with_backoff(fn, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            return fn()
        except HttpError as exc:
            if exc.resp.status in (429, 403) and attempt < max_retries - 1:
                wait = 2 ** attempt
                log.warning("gmail_quota_backoff", attempt=attempt, wait_seconds=wait)
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
    body_data = payload.get("body", {}).get("data", "")
    if body_data:
        return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")
    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/plain":
            data = part.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    return ""


def _extract_new_message_ids_from_history(history: list[dict]) -> list[str]:
    """Pull message IDs from messagesAdded events in a history response."""
    ids = []
    for entry in history:
        for added in entry.get("messagesAdded", []):
            msg_id = added.get("message", {}).get("id")
            if msg_id:
                ids.append(msg_id)
    return ids


def _fetch_message_ids_delta(service, history_id: str) -> tuple[list[str], str]:
    """Fetch new message IDs since history_id. Returns (ids, new_history_id)."""
    all_history = []
    page_token = None
    new_history_id = history_id

    while True:
        kwargs = {"userId": "me", "startHistoryId": history_id, "historyTypes": ["messageAdded"]}
        if page_token:
            kwargs["pageToken"] = page_token

        result = _with_backoff(lambda: service.users().history().list(**kwargs).execute())  # noqa: B023
        all_history.extend(result.get("history", []))
        new_history_id = result.get("historyId", new_history_id)
        page_token = result.get("nextPageToken")
        if not page_token:
            break

    return _extract_new_message_ids_from_history(all_history), new_history_id


def _fetch_message_ids_full(service, max_results: int) -> tuple[list[str], str]:
    """Fallback: fetch recent message IDs via messages.list. Returns (ids, historyId)."""
    result = _with_backoff(lambda: (
        service.users()
        .messages()
        .list(userId="me", labelIds=["INBOX", "UNREAD"], maxResults=max_results)
        .execute()
    ))
    ids = [m["id"] for m in result.get("messages", [])]

    # Get the current historyId from profile for next delta poll
    profile = _with_backoff(lambda: service.users().getProfile(userId="me").execute())
    history_id = str(profile.get("historyId", ""))

    return ids, history_id


def _fetch_and_store_message(service, msg_id: str, user_id: str, source_id: str, fmt: str) -> bool:
    """Fetch a single Gmail message and store as RawEvent. Returns True if inserted."""
    msg: dict = _with_backoff(lambda: (  # noqa: B023
        service.users().messages().get(userId="me", id=msg_id, format=fmt).execute()
    ))

    payload = msg.get("payload", {})
    headers = payload.get("headers", [])
    body_text = _decode_body(payload) if fmt == "full" else ""

    raw_payload = {
        "gmail_id": msg_id,
        "thread_id": msg.get("threadId"),
        "snippet": msg.get("snippet", ""),
        "label_ids": msg.get("labelIds", []),
        "internal_date": msg.get("internalDate"),
        "sender": _extract_header(headers, "From"),
        "subject": _extract_header(headers, "Subject"),
        "body_text": body_text[:10_000],
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
            log.info("raw_event_inserted", external_id=msg_id, user_id=user_id)
            return True
        except Exception:
            db.rollback()
            return False


def poll_gmail(user_id: str, source_id: str) -> int:
    """
    Poll Gmail inbox for new messages and store as raw_events.
    Uses History API delta when a sync_cursor (historyId) exists; falls back
    to messages.list on first run.
    Returns count of newly inserted raw_events.
    """
    settings = get_settings()
    service = _build_service()
    fmt = "full" if settings.privacy_store_full_bodies else "metadata"

    with get_db() as db:
        source = db.query(Source).filter_by(id=source_id).first()
        cursor = source.sync_cursor if source else None

    if cursor:
        log.info("gmail_delta_poll_start", history_id=cursor, user_id=user_id)
        try:
            message_ids, new_cursor = _fetch_message_ids_delta(service, cursor)
        except HttpError as exc:
            if exc.resp.status == 404:
                # historyId expired (>30 days) — fall back to full list
                log.warning("gmail_history_expired_fallback", user_id=user_id)
                message_ids, new_cursor = _fetch_message_ids_full(service, settings.gmail_max_results)
            else:
                raise
    else:
        log.info("gmail_full_poll_start", user_id=user_id)
        message_ids, new_cursor = _fetch_message_ids_full(service, settings.gmail_max_results)

    # Deduplicate against existing raw_events
    with get_db() as db:
        existing_ids: set[str] = {
            row.external_id
            for row in db.query(RawEvent.external_id).filter(
                RawEvent.user_id == user_id,
                RawEvent.source_id == source_id,
                RawEvent.external_id.isnot(None),
            )
        }

    inserted = 0
    for msg_id in message_ids:
        if msg_id not in existing_ids:
            if _fetch_and_store_message(service, msg_id, user_id, source_id, fmt):
                inserted += 1

    # Update source cursor + last_synced_at
    with get_db() as db:
        source = db.query(Source).filter_by(id=source_id).first()
        if source:
            source.sync_cursor = new_cursor
            source.last_synced_at = datetime.now(tz=timezone.utc)
            db.commit()

    log.info("gmail_poll_complete", inserted=inserted, user_id=user_id, source_id=source_id, new_cursor=new_cursor)
    return inserted
