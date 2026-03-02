# tests/unit/test_circuit_breaker.py
"""Unit tests for CircuitBreaker — no external deps."""
from datetime import datetime, timezone, timedelta
import pytest

from core.circuit_breaker import CircuitBreaker


def test_breaker_starts_closed():
    cb = CircuitBreaker("test")
    assert not cb.is_open()


def test_breaker_opens_at_threshold():
    cb = CircuitBreaker("test", threshold=3)
    cb.record_failure()
    cb.record_failure()
    assert not cb.is_open()  # still below threshold
    cb.record_failure()
    assert cb.is_open()


def test_breaker_stays_closed_below_threshold():
    cb = CircuitBreaker("test", threshold=5)
    for _ in range(4):
        cb.record_failure()
    assert not cb.is_open()


def test_record_success_resets_counter():
    cb = CircuitBreaker("test", threshold=3)
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    assert not cb.is_open()
    assert cb._failures == 0


def test_record_success_opens_tripped_circuit():
    cb = CircuitBreaker("test", threshold=2)
    cb.record_failure()
    cb.record_failure()
    assert cb.is_open()
    cb.record_success()
    assert not cb.is_open()


def test_breaker_auto_resets_after_timeout():
    cb = CircuitBreaker("test", threshold=2, reset_minutes=10)
    cb.record_failure()
    cb.record_failure()
    assert cb.is_open()
    # Simulate the reset window having elapsed
    cb._tripped_at = datetime.now(timezone.utc) - timedelta(minutes=11)
    assert not cb.is_open()
    assert cb._failures == 0


def test_auto_reset_before_timeout_stays_open():
    cb = CircuitBreaker("test", threshold=2, reset_minutes=10)
    cb.record_failure()
    cb.record_failure()
    cb._tripped_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    assert cb.is_open()


def test_multiple_failures_beyond_threshold_does_not_reset():
    cb = CircuitBreaker("test", threshold=3)
    for _ in range(10):
        cb.record_failure()
    assert cb.is_open()
