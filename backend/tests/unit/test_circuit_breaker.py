"""Circuit breaker: fails fast after repeated Ollama failures
instead of paying the full request timeout on every call while it's down."""

import time

from app.core.circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState


def test_starts_closed():
    breaker = CircuitBreaker(failure_threshold=3, reset_timeout_seconds=30.0)
    assert breaker.state == CircuitState.CLOSED
    breaker.before_call()  # must not raise


def test_opens_after_threshold_failures():
    breaker = CircuitBreaker(failure_threshold=3, reset_timeout_seconds=30.0)
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == CircuitState.CLOSED  # not yet at threshold
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN


def test_open_breaker_fails_fast():
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout_seconds=30.0)
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN

    try:
        breaker.before_call()
        assert False, "expected CircuitOpenError"
    except CircuitOpenError:
        pass


def test_success_resets_failure_count():
    breaker = CircuitBreaker(failure_threshold=3, reset_timeout_seconds=30.0)
    breaker.record_failure()
    breaker.record_failure()
    breaker.record_success()
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == CircuitState.CLOSED  # count was reset, not yet at threshold


def test_transitions_to_half_open_after_cooldown():
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout_seconds=0.05)
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN

    time.sleep(0.1)
    assert breaker.state == CircuitState.HALF_OPEN
    breaker.before_call()  # half-open must allow a trial call through


def test_failed_half_open_trial_reopens_immediately():
    breaker = CircuitBreaker(failure_threshold=5, reset_timeout_seconds=0.05)
    breaker.record_failure()
    breaker._state = CircuitState.OPEN  # force open regardless of threshold for this test
    breaker._opened_at = time.monotonic() - 1  # already past cooldown

    assert breaker.state == CircuitState.HALF_OPEN
    breaker.record_failure()  # the trial call failed
    assert breaker.state == CircuitState.OPEN


def test_successful_half_open_trial_closes():
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout_seconds=0.05)
    breaker.record_failure()
    time.sleep(0.1)
    assert breaker.state == CircuitState.HALF_OPEN

    breaker.record_success()
    assert breaker.state == CircuitState.CLOSED
