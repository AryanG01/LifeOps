"""Outlook mail poller via Microsoft Graph delta sync."""
from datetime import datetime, timezone
from html.parser import HTMLParser

import httpx
import structlog

from connectors.outlook.auth import get_token_dict
from core.db.engine import get_db
from core.db.models import RawEvent, Source

log = structlog.get_logger()

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
MAIL_DELTA_URL = (
    f"{GRAPH_BASE}/me/mailFolders/inbox/messages/delta"
    "?$select=id,subject,from,receivedDateTime,bodyPreview,body,isRead,categories&$top=50"
)


class _HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._text = []

    def handle_data(self, data):
        self._text.append(data)

    def get_text(self):
        return " ".join(self._text).strip()


def _strip_html(html: str) -> str:
    s = _HTMLStripper()
    s.feed(html)
    return s.get_text()


def _extract_message_fields(graph_msg: dict) -> dict:
    """Normalise a Graph API message object into our field names."""
    sender_info = graph_msg.get("from", {}).get("emailAddress", {})
    body = graph_msg.get("body", {})
    body_text = (
        _strip_html(body.get("content", ""))
        if body.get("contentType") == "html"
        else body.get("content", "")
    )

    return {
        "external_id": graph_msg["id"],
        "sender": sender_info.get("address", "unknown"),
        "sender_name": sender_info.get("name", ""),
        "title": graph_msg.get("subject", "(no subject)"),
        "body_preview": graph_msg.get("bodyPreview", "")[:500],
        "body_full": body_text[:10_000],
        "received_at": graph_msg.get("receivedDateTime", ""),
        "is_read": graph_msg.get("isRead", False),
        "categories": graph_msg.get("categories", []),
    }


def _graph_get(url: str, token: dict) -> dict:
    headers = {"Authorization": f"Bearer {token['access_token']}", "Accept": "application/json"}
    resp = httpx.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def poll_outlook(user_id: str, source_id: str) -> int:
    """
    Poll Outlook inbox via Graph delta sync.
    Stores deltaLink as sync_cursor on Source.
    Returns count of new raw_events inserted.
    """
    token = get_token_dict()
    inserted = 0

    with get_db() as db:
        source = db.query(Source).filter_by(id=source_id).first()
        delta_link = source.sync_cursor if source else None

    url = delta_link or MAIL_DELTA_URL
    new_delta_link = None

    while url:
        data = _graph_get(url, token)
        messages = data.get("value", [])

        for msg in messages:
            if msg.get("@odata.type") == "#microsoft.graph.message":
                fields = _extract_message_fields(msg)
                with get_db() as db:
                    exists = db.query(RawEvent).filter_by(
                        user_id=user_id, source_id=source_id, external_id=fields["external_id"]
                    ).first()
                    if not exists:
                        db.add(RawEvent(
                            user_id=user_id,
                            source_id=source_id,
                            external_id=fields["external_id"],
                            payload_json=fields,
                        ))
                        db.commit()
                        log.info("outlook_message_inserted", external_id=fields["external_id"][:12])
                        inserted += 1

        new_delta_link = data.get("@odata.deltaLink", new_delta_link)
        url = data.get("@odata.nextLink")  # None when pagination exhausted

    if new_delta_link:
        with get_db() as db:
            source = db.query(Source).filter_by(id=source_id).first()
            if source:
                source.sync_cursor = new_delta_link
                source.last_synced_at = datetime.now(tz=timezone.utc)
                db.commit()

    log.info("outlook_poll_complete", inserted=inserted, source_id=source_id, user_id=user_id)
    return inserted
