# tests/unit/test_normalizer_multisource.py
"""Tests for _extract_fields_from_payload (pure function, no DB needed)
and the two date-parsing helpers."""
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# _extract_fields_from_payload — Gmail path
# ---------------------------------------------------------------------------

def test_gmail_path_detected_by_gmail_id_key():
    from core.pipeline.normalizer import _extract_fields_from_payload
    payload = {
        "gmail_id": "abc123",
        "sender": "alice@example.com",
        "subject": "Hello",
        "body_text": "Full body",
        "internal_date": "1700000000000",
        "label_ids": ["INBOX", "UNREAD"],
    }
    result = _extract_fields_from_payload(payload, None)
    assert result["external_id"] == "abc123"
    assert result["sender"] == "alice@example.com"
    assert result["subject"] == "Hello"
    assert result["body"] == "Full body"
    assert result["label_ids"] == ["INBOX", "UNREAD"]


def test_gmail_path_falls_back_to_snippet_when_no_body_text():
    from core.pipeline.normalizer import _extract_fields_from_payload
    payload = {
        "gmail_id": "abc123",
        "sender": "alice@example.com",
        "subject": "Hello",
        "snippet": "Snippet text here",
        "internal_date": "1700000000000",
    }
    result = _extract_fields_from_payload(payload, None)
    assert result["body"] == "Snippet text here"


def test_gmail_path_external_id_falls_back_to_event_arg():
    from core.pipeline.normalizer import _extract_fields_from_payload
    payload = {"gmail_id": "gid", "sender": "", "subject": ""}
    result = _extract_fields_from_payload(payload, "event-fallback")
    # gmail_id takes precedence over event external_id
    assert result["external_id"] == "gid"


def test_gmail_path_message_ts_is_timezone_aware():
    from core.pipeline.normalizer import _extract_fields_from_payload
    payload = {"gmail_id": "gid", "sender": "", "subject": "", "internal_date": "1700000000000"}
    result = _extract_fields_from_payload(payload, None)
    assert result["message_ts"].tzinfo is not None


# ---------------------------------------------------------------------------
# _extract_fields_from_payload — Outlook path
# ---------------------------------------------------------------------------

def test_outlook_path_detected_when_no_gmail_id():
    from core.pipeline.normalizer import _extract_fields_from_payload
    payload = {
        "sender": "bob@nusoutlook.com",
        "title": "NUS Update",
        "body_full": "Full email body",
        "external_id": "outlook-ext-id",
        "received_at": "2026-01-15T10:00:00Z",
    }
    result = _extract_fields_from_payload(payload, None)
    assert result["external_id"] == "outlook-ext-id"
    assert result["sender"] == "bob@nusoutlook.com"
    assert result["subject"] == "NUS Update"
    assert result["body"] == "Full email body"
    assert result["label_ids"] == []


def test_outlook_path_falls_back_to_body_preview():
    from core.pipeline.normalizer import _extract_fields_from_payload
    payload = {
        "sender": "bob@nusoutlook.com",
        "title": "Test",
        "body_preview": "Preview only",
        "external_id": "eid",
        "received_at": "2026-01-15T10:00:00Z",
    }
    result = _extract_fields_from_payload(payload, None)
    assert result["body"] == "Preview only"


def test_outlook_path_falls_back_to_event_external_id():
    from core.pipeline.normalizer import _extract_fields_from_payload
    payload = {"sender": "bob@nusoutlook.com", "title": "Test"}
    result = _extract_fields_from_payload(payload, "fallback-id")
    assert result["external_id"] == "fallback-id"


def test_outlook_path_message_ts_is_timezone_aware():
    from core.pipeline.normalizer import _extract_fields_from_payload
    payload = {
        "sender": "x@y.com",
        "title": "s",
        "received_at": "2026-01-15T10:30:00Z",
        "external_id": "eid",
    }
    result = _extract_fields_from_payload(payload, None)
    assert result["message_ts"].tzinfo is not None


# ---------------------------------------------------------------------------
# _parse_gmail_date
# ---------------------------------------------------------------------------

def test_gmail_date_parsed_from_epoch_ms():
    from core.pipeline.normalizer import _parse_gmail_date
    result = _parse_gmail_date("1700000000000")
    assert result.tzinfo is not None
    assert result.year == 2023


def test_gmail_date_invalid_string_returns_now():
    from core.pipeline.normalizer import _parse_gmail_date
    before = datetime.now(tz=timezone.utc)
    result = _parse_gmail_date("not-a-number")
    after = datetime.now(tz=timezone.utc)
    assert before <= result <= after


def test_gmail_date_none_returns_now():
    from core.pipeline.normalizer import _parse_gmail_date
    before = datetime.now(tz=timezone.utc)
    result = _parse_gmail_date(None)
    after = datetime.now(tz=timezone.utc)
    assert before <= result <= after


# ---------------------------------------------------------------------------
# _parse_outlook_date
# ---------------------------------------------------------------------------

def test_outlook_date_parsed_from_iso_z_suffix():
    from core.pipeline.normalizer import _parse_outlook_date
    result = _parse_outlook_date("2026-01-15T10:30:00Z")
    assert result.tzinfo is not None
    assert result.year == 2026
    assert result.month == 1
    assert result.day == 15
    assert result.hour == 10


def test_outlook_date_invalid_returns_now():
    from core.pipeline.normalizer import _parse_outlook_date
    before = datetime.now(tz=timezone.utc)
    result = _parse_outlook_date("not-a-date")
    after = datetime.now(tz=timezone.utc)
    assert before <= result <= after


def test_outlook_date_none_returns_now():
    from core.pipeline.normalizer import _parse_outlook_date
    before = datetime.now(tz=timezone.utc)
    result = _parse_outlook_date(None)
    after = datetime.now(tz=timezone.utc)
    assert before <= result <= after
