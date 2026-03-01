# tests/unit/test_pvi.py
from core.pvi.engine import score_from_features, classify_regime, POLICY_MAP


def _features(**kwargs):
    base = {"tasks_open": 0, "tasks_overdue": 0,
            "inbox_unread": 0, "incoming_24h": 0, "calendar_minutes": 0}
    base.update(kwargs)
    return base


def test_calm_state_reduces_score():
    score, explanation = score_from_features(_features())
    # Calm state: overdue=0, open<=3, incoming<5 → -10 from baseline 50
    assert score == 40
    assert "calm_state" in explanation


def test_overdue_tasks_increase_score():
    score, explanation = score_from_features(_features(tasks_open=5, tasks_overdue=3))
    assert score > 50
    assert "tasks_overdue" in explanation


def test_overdue_cap_at_25():
    # 10 overdue → would be 100 pts but capped at 25
    score, explanation = score_from_features(_features(tasks_overdue=10, tasks_open=0))
    # 50 + 25 (capped) = 75, no calm bonus (overdue>0)
    assert score == 75
    assert "tasks_overdue=10 (+25)" in explanation


def test_many_open_tasks_adds_points():
    score, _ = score_from_features(_features(tasks_open=15, tasks_overdue=0))
    assert score > 50


def test_inbox_pressure_adds_points():
    score, explanation = score_from_features(_features(inbox_unread=55, tasks_overdue=0))
    assert score > 50
    assert "inbox_pressure" in explanation


def test_score_clamped_at_0_to_100():
    score, _ = score_from_features(_features(tasks_overdue=20, tasks_open=20,
                                             inbox_unread=100, incoming_24h=50))
    assert 0 <= score <= 100


def test_overloaded_regime():
    assert classify_regime(80) == "overloaded"
    assert classify_regime(75) == "overloaded"


def test_peak_regime():
    assert classify_regime(65) == "peak"
    assert classify_regime(60) == "peak"


def test_normal_regime():
    assert classify_regime(50) == "normal"
    assert classify_regime(40) == "normal"


def test_recovery_regime():
    assert classify_regime(39) == "recovery"
    assert classify_regime(20) == "recovery"


def test_policy_map_completeness():
    for regime in ["overloaded", "peak", "normal", "recovery"]:
        policy = POLICY_MAP[regime]
        assert "max_digest_items" in policy
        assert "reminder_cadence" in policy
        assert "escalation_level" in policy
        assert "auto_activate" in policy
