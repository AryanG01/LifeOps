from connectors.outlook.poller import _extract_message_fields


def test_extract_message_fields_basic():
    graph_msg = {
        "id": "AAMk123",
        "subject": "Assignment due Friday",
        "from": {"emailAddress": {"address": "prof@nus.edu.sg", "name": "Prof Tan"}},
        "receivedDateTime": "2026-03-02T10:00:00Z",
        "bodyPreview": "Please submit by 11:59pm",
        "body": {"content": "<p>Please submit by 11:59pm</p>", "contentType": "html"},
        "isRead": False,
    }
    fields = _extract_message_fields(graph_msg)
    assert fields["external_id"] == "AAMk123"
    assert fields["sender"] == "prof@nus.edu.sg"
    assert fields["title"] == "Assignment due Friday"
    assert "submit" in fields["body_preview"]


def test_extract_message_fields_plain_body():
    graph_msg = {
        "id": "BBMk456",
        "subject": "Meeting notes",
        "from": {"emailAddress": {"address": "team@company.com", "name": "Team"}},
        "receivedDateTime": "2026-03-02T12:00:00Z",
        "bodyPreview": "See notes below",
        "body": {"content": "See notes below with details", "contentType": "text"},
        "isRead": True,
    }
    fields = _extract_message_fields(graph_msg)
    assert fields["external_id"] == "BBMk456"
    assert fields["sender"] == "team@company.com"
    assert fields["is_read"] is True
    assert "See notes below" in fields["body_full"]
