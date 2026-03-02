# tests/unit/test_meeting_prep.py
from unittest.mock import MagicMock, patch


def _make_event(title, attendees=None):
    e = MagicMock()
    e.title = title
    e.id = "event-uuid-1234"
    e.attendees_json = attendees or []
    return e


def _make_cm(mock_db):
    cm = MagicMock()
    cm.__enter__.return_value = mock_db
    cm.__exit__.return_value = False
    return cm


def test_empty_window_returns_empty_list():
    """No events in 15-45 min window → empty list, no LLM call."""
    mock_db = MagicMock()
    event_chain = MagicMock()
    event_chain.filter.return_value.all.return_value = []
    mock_db.query.side_effect = [event_chain]

    with patch("core.db.engine.get_db", return_value=_make_cm(mock_db)):
        from core.calendar.prep import generate_prep_for_upcoming
        result = generate_prep_for_upcoming("user-1")

    assert result == []


def test_one_event_returns_one_message():
    """One upcoming event → LLM called, one Telegram message returned."""
    event = _make_event("Team Standup", attendees=["alice@example.com"])

    mock_db = MagicMock()
    event_chain = MagicMock()
    event_chain.filter.return_value.all.return_value = [event]

    msg_chain = MagicMock()
    msg_chain.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
    mock_db.query.side_effect = [event_chain, msg_chain]

    with patch("core.db.engine.get_db", return_value=_make_cm(mock_db)), \
         patch("core.llm.extractor._call_llm_raw", return_value="• Know this\n• Prepare that\n• Open Q"):
        from core.calendar.prep import generate_prep_for_upcoming
        result = generate_prep_for_upcoming("user-1")

    assert len(result) == 1
    assert "Team Standup" in result[0]
    assert "30min" in result[0]


def test_event_message_includes_llm_summary():
    """LLM output appears (truncated) in the returned message."""
    event = _make_event("Budget Review")

    mock_db = MagicMock()
    event_chain = MagicMock()
    event_chain.filter.return_value.all.return_value = [event]

    msg_chain = MagicMock()
    msg_chain.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
    mock_db.query.side_effect = [event_chain, msg_chain]

    llm_output = "• Check quarterly numbers\n• Prepare slides\n• Ask about headcount"

    with patch("core.db.engine.get_db", return_value=_make_cm(mock_db)), \
         patch("core.llm.extractor._call_llm_raw", return_value=llm_output):
        from core.calendar.prep import generate_prep_for_upcoming
        result = generate_prep_for_upcoming("user-1")

    assert "quarterly numbers" in result[0]


def test_llm_failure_skips_event_gracefully():
    """LLM raises exception → event skipped, no exception propagated."""
    event = _make_event("Crash Meeting")

    mock_db = MagicMock()
    event_chain = MagicMock()
    event_chain.filter.return_value.all.return_value = [event]

    msg_chain = MagicMock()
    msg_chain.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
    mock_db.query.side_effect = [event_chain, msg_chain]

    with patch("core.db.engine.get_db", return_value=_make_cm(mock_db)), \
         patch("core.llm.extractor._call_llm_raw", side_effect=Exception("LLM timeout")):
        from core.calendar.prep import generate_prep_for_upcoming
        result = generate_prep_for_upcoming("user-1")

    assert result == []


def test_related_emails_surfaced_in_llm_prompt(monkeypatch):
    """When related messages exist, their previews are passed to the LLM."""
    event = _make_event("1:1 with Alice", attendees=["alice@example.com"])

    related_msg = MagicMock()
    related_msg.sender = "alice@example.com"
    related_msg.title = "Follow-up"
    related_msg.body_preview = "Let's discuss the roadmap"

    mock_db = MagicMock()
    event_chain = MagicMock()
    event_chain.filter.return_value.all.return_value = [event]

    msg_chain = MagicMock()
    msg_chain.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [related_msg]
    mock_db.query.side_effect = [event_chain, msg_chain]

    captured_prompts = []

    def fake_llm(system, prompt):
        captured_prompts.append(prompt)
        return "Prep summary"

    with patch("core.db.engine.get_db", return_value=_make_cm(mock_db)), \
         patch("core.llm.extractor._call_llm_raw", side_effect=fake_llm):
        from core.calendar.prep import generate_prep_for_upcoming
        generate_prep_for_upcoming("user-1")

    assert len(captured_prompts) == 1
    assert "alice@example.com" in captured_prompts[0]
    assert "roadmap" in captured_prompts[0]
