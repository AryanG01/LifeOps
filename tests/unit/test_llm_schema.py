# tests/unit/test_llm_schema.py
import pytest
from pydantic import ValidationError
from core.schemas.llm import ExtractionResult

VALID_EXTRACTION = {
    "labels": [{"label": "coursework", "confidence": 0.9}],
    "summary_short": "Assignment due Monday",
    "summary_long": "Detailed summary here.",
    "action_items": [{
        "title": "Submit assignment",
        "details": "Upload PDF",
        "due_at": "2026-03-09T23:59:00+08:00",
        "priority": 85,
        "confidence": 0.8,
    }],
    "reply_drafts": [],
    "urgency": 0.7,
}


def test_valid_extraction_parses():
    result = ExtractionResult.model_validate(VALID_EXTRACTION)
    assert len(result.action_items) == 1
    assert result.urgency == 0.7


def test_extra_key_raises():
    bad = {**VALID_EXTRACTION, "unexpected_field": "bad"}
    with pytest.raises(ValidationError):
        ExtractionResult.model_validate(bad)


def test_urgency_out_of_range_raises():
    bad = {**VALID_EXTRACTION, "urgency": 1.5}
    with pytest.raises(ValidationError):
        ExtractionResult.model_validate(bad)


def test_missing_summary_short_raises():
    bad = {k: v for k, v in VALID_EXTRACTION.items() if k != "summary_short"}
    with pytest.raises(ValidationError):
        ExtractionResult.model_validate(bad)


def test_empty_action_items_valid():
    data = {**VALID_EXTRACTION, "action_items": []}
    result = ExtractionResult.model_validate(data)
    assert result.action_items == []


def test_multiple_labels_valid():
    data = {**VALID_EXTRACTION, "labels": [
        {"label": "coursework", "confidence": 0.9},
        {"label": "deadline", "confidence": 0.7},
    ]}
    result = ExtractionResult.model_validate(data)
    assert len(result.labels) == 2
