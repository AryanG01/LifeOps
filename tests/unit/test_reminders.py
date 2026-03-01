# tests/unit/test_reminders.py
from datetime import timedelta
from core.pipeline.reminders import CADENCES


def test_all_cadences_exist():
    for name in ["gentle", "standard", "aggressive"]:
        assert name in CADENCES


def test_standard_cadence_has_three_offsets():
    assert len(CADENCES["standard"]) == 3


def test_gentle_cadence_has_two_offsets():
    assert len(CADENCES["gentle"]) == 2


def test_aggressive_cadence_has_five_offsets():
    assert len(CADENCES["aggressive"]) == 5


def test_reminder_offsets_are_timedeltas():
    for cadence in CADENCES.values():
        for offset in cadence:
            assert isinstance(offset, timedelta)


def test_offsets_are_positive():
    for cadence in CADENCES.values():
        for offset in cadence:
            assert offset.total_seconds() > 0


def test_standard_cadence_order():
    # Largest offset first (furthest from due date)
    offsets = CADENCES["standard"]
    for i in range(len(offsets) - 1):
        assert offsets[i] > offsets[i + 1]
