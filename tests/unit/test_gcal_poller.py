from connectors.gcal.poller import _parse_event_fields


def test_parse_event_fields_timed():
    event = {
        "id": "abc123",
        "summary": "CS3230 Lecture",
        "start": {"dateTime": "2026-03-05T10:00:00+08:00"},
        "end": {"dateTime": "2026-03-05T12:00:00+08:00"},
        "location": "LT19",
        "attendees": [{"email": "a@nus.edu.sg"}],
        "description": "Week 8 lecture",
    }
    fields = _parse_event_fields(event)
    assert fields["external_id"] == "abc123"
    assert fields["title"] == "CS3230 Lecture"
    assert fields["is_all_day"] is False
    assert fields["location"] == "LT19"
    assert "a@nus.edu.sg" in fields["attendees_json"]
    assert fields["description"] == "Week 8 lecture"


def test_parse_event_fields_all_day():
    event = {
        "id": "def456",
        "summary": "Holiday",
        "start": {"date": "2026-03-10"},
        "end": {"date": "2026-03-11"},
    }
    fields = _parse_event_fields(event)
    assert fields["is_all_day"] is True
    assert fields["external_id"] == "def456"
    assert fields["title"] == "Holiday"


def test_parse_event_fields_no_summary():
    event = {
        "id": "ghi789",
        "start": {"dateTime": "2026-03-05T14:00:00+00:00"},
        "end": {"dateTime": "2026-03-05T15:00:00+00:00"},
    }
    fields = _parse_event_fields(event)
    assert fields["title"] == "(no title)"
    assert fields["is_all_day"] is False
