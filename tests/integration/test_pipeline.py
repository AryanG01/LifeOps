# tests/integration/test_pipeline.py
"""
End-to-end pipeline tests using a real Postgres test database (clawdbot_test).

Requires:
  - DATABASE_URL=postgresql://clawdbot:clawdbot@localhost/clawdbot_test set in env
  - Run: cd infra && alembic upgrade head (against clawdbot_test DB)

Run with: pytest tests/integration/ -v
"""
import json
import pytest
from unittest.mock import patch, MagicMock

FAKE_EXTRACTION = json.dumps({
    "labels": [{"label": "coursework", "confidence": 0.9}],
    "summary_short": "Test assignment due",
    "summary_long": None,
    "action_items": [{
        "title": "Submit test assignment",
        "details": "Upload to Canvas",
        "due_at": None,
        "priority": 70,
        "confidence": 0.8,
    }],
    "reply_drafts": [],
    "urgency": 0.6,
})


@pytest.mark.integration
def test_pipeline_normalize_roundtrip(db_user_source):
    """
    Insert a raw_event and verify normalize_raw_event creates a Message.
    """
    from core.db.engine import get_db
    from core.db.models import RawEvent, Message
    from core.pipeline.normalizer import normalize_raw_event

    user_id, source_id = db_user_source

    with get_db() as db:
        event = RawEvent(
            user_id=user_id,
            source_id=source_id,
            external_id="test-gmail-001",
            payload_json={
                "gmail_id": "test-gmail-001",
                "sender": "test@example.com",
                "subject": "Test Message",
                "body_text": "Hello world",
                "internal_date": "1700000000000",
            },
        )
        db.add(event)
        db.commit()
        event_id = str(event.id)

    msg_id = normalize_raw_event(event_id)
    assert msg_id is not None

    with get_db() as db:
        msg = db.query(Message).filter_by(id=msg_id).first()
        assert msg is not None
        assert msg.sender == "test@example.com"
        assert msg.title == "Test Message"
        assert msg.is_canvas is False


@pytest.mark.integration
def test_dedup_idempotent(db_user_source):
    """Normalizing the same raw_event twice does not create duplicate messages."""
    from core.db.engine import get_db
    from core.db.models import RawEvent, Message
    from core.pipeline.normalizer import normalize_raw_event

    user_id, source_id = db_user_source

    with get_db() as db:
        event = RawEvent(
            user_id=user_id,
            source_id=source_id,
            external_id="test-dedup-002",
            payload_json={
                "gmail_id": "test-dedup-002",
                "sender": "dedup@example.com",
                "subject": "Dedup Test",
                "body_text": "body",
            },
        )
        db.add(event)
        db.commit()
        event_id = str(event.id)

    msg_id_1 = normalize_raw_event(event_id)
    # Reset processed_at to allow re-processing (simulates retry)
    with get_db() as db:
        ev = db.query(RawEvent).filter_by(id=event_id).first()
        ev.processed_at = None
        db.commit()

    msg_id_2 = normalize_raw_event(event_id)
    # Second call should return None (deduped)
    assert msg_id_2 is None

    with get_db() as db:
        count = db.query(Message).filter_by(user_id=user_id).filter(
            Message.external_id == "test-dedup-002"
        ).count()
    assert count == 1


@pytest.mark.integration
def test_llm_extraction_creates_action_items(db_user_source):
    """LLM extraction creates action items for a message."""
    from core.db.engine import get_db
    from core.db.models import RawEvent, ActionItem
    from core.pipeline.normalizer import normalize_raw_event
    from core.llm.extractor import extract_all_pending

    user_id, source_id = db_user_source

    with get_db() as db:
        event = RawEvent(
            user_id=user_id,
            source_id=source_id,
            external_id="test-llm-003",
            payload_json={
                "gmail_id": "test-llm-003",
                "sender": "canvas@instructure.com",
                "subject": "CS3230 Assignment due",
                "body_text": "Assignment due in 3 days",
                "label_ids": ["INBOX", "UNREAD"],
            },
        )
        db.add(event)
        db.commit()
        event_id = str(event.id)

    normalize_raw_event(event_id)

    fake_message = MagicMock()
    fake_message.content = [MagicMock(text=FAKE_EXTRACTION)]
    fake_message.usage = MagicMock(input_tokens=100, output_tokens=50)

    with patch("core.llm.extractor._call_llm", return_value=(FAKE_EXTRACTION, 100, 50)):
        success, failed = extract_all_pending("v1")

    assert success >= 1
    with get_db() as db:
        items = db.query(ActionItem).filter_by(user_id=user_id).all()
    assert len(items) >= 1
    assert any("Submit" in item.title for item in items)
