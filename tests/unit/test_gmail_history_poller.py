from unittest.mock import MagicMock, patch
from connectors.gmail.poller import _extract_new_message_ids_from_history


def test_extract_history_returns_added_ids():
    history = [
        {"messagesAdded": [{"message": {"id": "abc"}}, {"message": {"id": "def"}}]},
        {"messagesAdded": [{"message": {"id": "ghi"}}]},
        {"labelsAdded": [{"message": {"id": "xyz"}}]},  # ignored
    ]
    result = _extract_new_message_ids_from_history(history)
    assert result == ["abc", "def", "ghi"]


def test_extract_history_empty():
    assert _extract_new_message_ids_from_history([]) == []
