# packages/core/src/core/circuit_breaker.py
"""
In-memory circuit breaker for protecting external API calls.

State is in-memory only — resets on worker restart (intentional).
A restart is a natural recovery signal; the 10-minute backoff window is short enough
that losing it on restart is acceptable.

Usage:
    from core.circuit_breaker import llm_breaker

    if llm_breaker.is_open():
        return  # skip this run

    try:
        result = call_llm(...)
        llm_breaker.record_success()
    except Exception:
        llm_breaker.record_failure()
"""
from datetime import datetime, timezone

import structlog

log = structlog.get_logger()


class CircuitBreaker:
    def __init__(self, name: str, threshold: int = 5, reset_minutes: int = 10):
        self.name = name
        self.threshold = threshold
        self.reset_minutes = reset_minutes
        self._failures: int = 0
        self._tripped_at: datetime | None = None

    def record_failure(self) -> None:
        """Increment failure count. Trip the breaker if threshold reached."""
        self._failures += 1
        if self._failures >= self.threshold and self._tripped_at is None:
            self._tripped_at = datetime.now(timezone.utc)
            log.warning("circuit_breaker_tripped", name=self.name, failures=self._failures)

    def record_success(self) -> None:
        """Reset failure count and close the circuit (resume normal calls)."""
        if self._failures > 0 or self._tripped_at is not None:
            log.info("circuit_breaker_reset", name=self.name)
        self._failures = 0
        self._tripped_at = None

    def is_open(self) -> bool:
        """
        Returns True if the circuit is open (calls should be skipped).
        Auto-resets after the reset window has elapsed.
        """
        if self._tripped_at is None:
            return False
        elapsed = (datetime.now(timezone.utc) - self._tripped_at).total_seconds()
        if elapsed >= self.reset_minutes * 60:
            self._failures = 0
            self._tripped_at = None
            log.info("circuit_breaker_auto_reset", name=self.name)
            return False
        return True


# Module-level instance — shared across all calls to job_extract_pending
llm_breaker = CircuitBreaker("llm")
