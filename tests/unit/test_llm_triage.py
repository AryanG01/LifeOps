from unittest.mock import patch
from core.llm.extractor import _is_actionable


def test_triage_returns_true_for_actionable():
    with patch("core.llm.extractor._call_llm_raw") as mock_llm:
        mock_llm.return_value = '{"actionable": true}'
        result = _is_actionable("Prof Tan", "Assignment due tomorrow", "Submit report by Friday 11:59pm")
        assert result is True


def test_triage_returns_false_for_receipt():
    with patch("core.llm.extractor._call_llm_raw") as mock_llm:
        mock_llm.return_value = '{"actionable": false}'
        result = _is_actionable("grab@grab.com", "Your receipt", "Total: $12.50")
        assert result is False


def test_triage_defaults_true_on_llm_error():
    """Fail open — if triage LLM errors, proceed with full extraction."""
    with patch("core.llm.extractor._call_llm_raw", side_effect=Exception("timeout")):
        result = _is_actionable("anyone@example.com", "subject", "body")
        assert result is True
