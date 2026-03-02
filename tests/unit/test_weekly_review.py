# tests/unit/test_weekly_review.py
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta


def _make_task(status, due_offset_hours=None):
    t = MagicMock()
    t.status = status
    t.due_at = (
        datetime.now(tz=timezone.utc) + timedelta(hours=due_offset_hours)
        if due_offset_hours is not None
        else None
    )
    t.title = "Test task title long enough to truncate at sixty characters x"
    return t


def _make_pvi(days_ago, score):
    p = MagicMock()
    p.date = (datetime.now(tz=timezone.utc) - timedelta(days=days_ago)).date()
    p.score = score
    return p


def _make_db(tasks, pvi_scores, email_count):
    mock_db = MagicMock()

    task_chain = MagicMock()
    task_chain.filter.return_value.all.return_value = tasks

    pvi_chain = MagicMock()
    pvi_chain.filter.return_value.order_by.return_value.all.return_value = pvi_scores

    msg_chain = MagicMock()
    msg_chain.filter.return_value.count.return_value = email_count

    mock_db.query.side_effect = [task_chain, pvi_chain, msg_chain]
    return mock_db


def _run(tasks, pvi_scores, email_count):
    mock_db = _make_db(tasks, pvi_scores, email_count)
    cm = MagicMock()
    cm.__enter__.return_value = mock_db
    cm.__exit__.return_value = False

    with patch("core.db.engine.get_db", return_value=cm):
        from core.digest.weekly import generate_weekly_review
        return generate_weekly_review("user-1")


def test_empty_db_returns_report_with_zeros():
    result = _run(tasks=[], pvi_scores=[], email_count=0)
    assert "Weekly Review" in result
    assert "0%" in result  # completion rate
    assert "Emails processed: 0" in result


def test_empty_pvi_sparkline_is_all_dots():
    result = _run(tasks=[], pvi_scores=[], email_count=0)
    assert "·" * 7 in result


def test_sparkline_score_gte_80_uses_full_block():
    result = _run(tasks=[], pvi_scores=[_make_pvi(0, 85)], email_count=0)
    assert "█" in result


def test_sparkline_score_60_to_79_uses_mid_high_block():
    result = _run(tasks=[], pvi_scores=[_make_pvi(0, 70)], email_count=0)
    assert "▆" in result


def test_sparkline_score_40_to_59_uses_mid_low_block():
    result = _run(tasks=[], pvi_scores=[_make_pvi(0, 45)], email_count=0)
    assert "▄" in result


def test_sparkline_score_lt_40_uses_small_block():
    result = _run(tasks=[], pvi_scores=[_make_pvi(0, 20)], email_count=0)
    assert "▂" in result


def test_overdue_tasks_appear_in_outstanding_section():
    overdue = _make_task("active", due_offset_hours=-48)
    done = _make_task("done")
    result = _run(tasks=[done, overdue], pvi_scores=[], email_count=3)
    assert "Still Outstanding" in result
    assert "⚠ Overdue: 1" in result
    assert "✓ Completed: 1" in result


def test_no_overdue_section_when_no_overdue_tasks():
    done = _make_task("done")
    result = _run(tasks=[done], pvi_scores=[], email_count=0)
    assert "Still Outstanding" not in result


def test_completion_rate_fifty_percent():
    done = _make_task("done")
    active = _make_task("active")  # no due_at → not overdue
    result = _run(tasks=[done, active], pvi_scores=[], email_count=0)
    assert "50%" in result


def test_avg_pvi_displayed_in_report():
    result = _run(tasks=[], pvi_scores=[_make_pvi(0, 80)], email_count=0)
    assert "avg: 80" in result


def test_email_count_shown_in_inbox_section():
    result = _run(tasks=[], pvi_scores=[], email_count=42)
    assert "Emails processed: 42" in result
