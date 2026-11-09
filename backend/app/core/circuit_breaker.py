"""In-process circuit breaker with open, half-open and closed states.
Repeated dependency failures trigger a cooldown; one trial call restores normal
operation after the dependency recovers."""

import time
from enum import Enum
from typing import Optional


class CircuitState(str, Enum):
    CLOSED = "closed"  # normal operation, calls go through
    OPEN = "open"  # failing fast, calls are rejected without trying
    HALF_OPEN = "half_open"  # cooldown elapsed, next call is a trial


class CircuitOpenError(Exception):
    """Raised by call sites when the breaker is open -- fail fast, don't even try."""


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, reset_timeout_seconds: float = 30.0) -> None:
        self.failure_threshold = failure_threshold
        self.reset_timeout_seconds = reset_timeout_seconds
        self._failure_count = 0
        self._state = CircuitState.CLOSED
        self._opened_at: Optional[float] = None

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN and self._opened_at is not None:
            if time.monotonic() - self._opened_at >= self.reset_timeout_seconds:
                self._state = CircuitState.HALF_OPEN
        return self._state

    def before_call(self) -> None:
        """Call before attempting the guarded operation. Raises CircuitOpenError if
        the breaker is open and the cooldown hasn't elapsed yet."""
        if self.state == CircuitState.OPEN:
            raise CircuitOpenError("Circuit breaker is open -- failing fast without calling")

    def record_success(self) -> None:
        self._failure_count = 0
        self._state = CircuitState.CLOSED
        self._opened_at = None

    def record_failure(self) -> None:
        self._failure_count += 1
        # A failed half-open trial re-opens immediately, regardless of the threshold --
        # one bad trial means the dependency isn't back yet.
        if self._state == CircuitState.HALF_OPEN or self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()
