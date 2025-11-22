"""Tests for resilience patterns (circuit breaker, exponential backoff, rate limiting)."""

from __future__ import annotations

import asyncio
from http import HTTPStatus
from unittest.mock import MagicMock

import pytest

from pythermacell.resilience import (
    CircuitBreaker,
    CircuitState,
    ExponentialBackoff,
    RateLimiter,
    retry_with_backoff,
)


class TestCircuitBreaker:
    """Test CircuitBreaker pattern."""

    def test_initial_state_is_closed(self) -> None:
        """Test that circuit breaker starts in CLOSED state."""
        breaker = CircuitBreaker()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.can_execute() is True

    def test_opens_after_failure_threshold(self) -> None:
        """Test that circuit opens after reaching failure threshold."""
        breaker = CircuitBreaker(failure_threshold=3)

        # Record 3 failures
        for _ in range(3):
            breaker.record_failure(Exception("test"))

        assert breaker.state == CircuitState.OPEN
        assert breaker.can_execute() is False

    def test_stays_closed_below_threshold(self) -> None:
        """Test that circuit stays closed below failure threshold."""
        breaker = CircuitBreaker(failure_threshold=5)

        # Record 4 failures (below threshold of 5)
        for _ in range(4):
            breaker.record_failure(Exception("test"))

        assert breaker.state == CircuitState.CLOSED
        assert breaker.can_execute() is True

    def test_success_resets_failure_count(self) -> None:
        """Test that success resets failure count in CLOSED state."""
        breaker = CircuitBreaker(failure_threshold=3)

        # Record 2 failures
        for _ in range(2):
            breaker.record_failure(Exception("test"))

        assert breaker.failure_count == 2

        # Record success - should reset
        breaker.record_success()

        assert breaker.failure_count == 0
        assert breaker.state == CircuitState.CLOSED

    async def test_enters_half_open_after_timeout(self) -> None:
        """Test that circuit enters HALF_OPEN state after recovery timeout."""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)

        # Open the circuit
        breaker.record_failure(Exception("test"))
        breaker.record_failure(Exception("test"))

        assert breaker.state == CircuitState.OPEN

        # Wait for recovery timeout
        await asyncio.sleep(0.15)

        # Check state - should be HALF_OPEN now
        assert breaker.state == CircuitState.HALF_OPEN
        assert breaker.can_execute() is True

    async def test_half_open_closes_after_success_threshold(self) -> None:
        """Test that HALF_OPEN closes after success threshold."""
        breaker = CircuitBreaker(
            failure_threshold=2,
            recovery_timeout=0.1,
            success_threshold=2,
        )

        # Open the circuit
        breaker.record_failure(Exception("test"))
        breaker.record_failure(Exception("test"))
        assert breaker.state == CircuitState.OPEN

        # Wait for recovery
        await asyncio.sleep(0.15)
        assert breaker.state == CircuitState.HALF_OPEN

        # Record successes
        breaker.record_success()
        assert breaker.state == CircuitState.HALF_OPEN  # Still half-open

        breaker.record_success()
        assert breaker.state == CircuitState.CLOSED  # Now closed

    async def test_half_open_reopens_on_failure(self) -> None:
        """Test that HALF_OPEN immediately reopens on any failure."""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)

        # Open the circuit
        breaker.record_failure(Exception("test"))
        breaker.record_failure(Exception("test"))

        # Wait for recovery
        await asyncio.sleep(0.15)
        assert breaker.state == CircuitState.HALF_OPEN

        # Any failure in HALF_OPEN should reopen circuit
        breaker.record_failure(Exception("test"))
        assert breaker.state == CircuitState.OPEN

    def test_reset_clears_state(self) -> None:
        """Test that reset clears all circuit breaker state."""
        breaker = CircuitBreaker(failure_threshold=2)

        # Open the circuit
        breaker.record_failure(Exception("test"))
        breaker.record_failure(Exception("test"))
        assert breaker.state == CircuitState.OPEN

        # Reset
        breaker.reset()

        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0
        assert breaker.can_execute() is True

    def test_only_monitors_specified_exceptions(self) -> None:
        """Test that circuit only monitors specific exception types."""
        breaker = CircuitBreaker(
            failure_threshold=2,
            monitored_exceptions=(ValueError, TypeError),
        )

        # RuntimeError should not be counted
        breaker.record_failure(RuntimeError("test"))
        assert breaker.failure_count == 0

        # ValueError should be counted
        breaker.record_failure(ValueError("test"))
        assert breaker.failure_count == 1

        # TypeError should be counted
        breaker.record_failure(TypeError("test"))
        assert breaker.failure_count == 2
        assert breaker.state == CircuitState.OPEN


class TestExponentialBackoff:
    """Test ExponentialBackoff pattern."""

    def test_initial_delay(self) -> None:
        """Test that first retry uses base delay."""
        backoff = ExponentialBackoff(base_delay=1.0, jitter=False)

        delay = backoff.calculate_delay(0)
        assert delay == 1.0

    def test_exponential_growth(self) -> None:
        """Test that delays grow exponentially."""
        backoff = ExponentialBackoff(
            base_delay=1.0,
            exponential_base=2.0,
            jitter=False,
        )

        assert backoff.calculate_delay(0) == 1.0  # 1 * 2^0
        assert backoff.calculate_delay(1) == 2.0  # 1 * 2^1
        assert backoff.calculate_delay(2) == 4.0  # 1 * 2^2
        assert backoff.calculate_delay(3) == 8.0  # 1 * 2^3

    def test_respects_max_delay(self) -> None:
        """Test that delay is capped at max_delay."""
        backoff = ExponentialBackoff(
            base_delay=1.0,
            max_delay=5.0,
            jitter=False,
        )

        # Attempt 5 should be 32 seconds, but capped at 5
        delay = backoff.calculate_delay(5)
        assert delay == 5.0

    def test_jitter_adds_randomness(self) -> None:
        """Test that jitter adds randomness to delays."""
        backoff = ExponentialBackoff(base_delay=10.0, jitter=True)

        delays = [backoff.calculate_delay(0) for _ in range(10)]

        # All delays should be between 0 and 10
        assert all(0 <= d <= 10.0 for d in delays)

        # Delays should not all be the same (very unlikely with jitter)
        assert len(set(delays)) > 1

    def test_max_retries_property(self) -> None:
        """Test that max_retries property works."""
        backoff = ExponentialBackoff(max_retries=7)
        assert backoff.max_retries == 7


class TestRateLimiter:
    """Test RateLimiter pattern."""

    def test_is_rate_limited_returns_true_for_429(self) -> None:
        """Test that 429 status is identified as rate limited."""
        assert RateLimiter.is_rate_limited(HTTPStatus.TOO_MANY_REQUESTS) is True

    def test_is_rate_limited_returns_false_for_other_status(self) -> None:
        """Test that non-429 status is not identified as rate limited."""
        assert RateLimiter.is_rate_limited(HTTPStatus.OK) is False
        assert RateLimiter.is_rate_limited(HTTPStatus.UNAUTHORIZED) is False
        assert RateLimiter.is_rate_limited(HTTPStatus.INTERNAL_SERVER_ERROR) is False

    def test_get_retry_delay_returns_zero_for_non_429(self) -> None:
        """Test that non-429 status returns zero delay."""
        limiter = RateLimiter()
        delay = limiter.get_retry_delay(HTTPStatus.OK, None)
        assert delay == 0.0

    def test_get_retry_delay_uses_default_without_header(self) -> None:
        """Test that default delay is used when no Retry-After header."""
        limiter = RateLimiter(default_retry_delay=45.0)
        delay = limiter.get_retry_delay(HTTPStatus.TOO_MANY_REQUESTS, None)
        assert delay == 45.0

    def test_get_retry_delay_parses_integer_header(self) -> None:
        """Test that Retry-After header with integer is parsed."""
        limiter = RateLimiter()
        delay = limiter.get_retry_delay(HTTPStatus.TOO_MANY_REQUESTS, "30")
        assert delay == 30.0

    def test_get_retry_delay_respects_max_delay(self) -> None:
        """Test that delay is capped at max_retry_delay."""
        limiter = RateLimiter(max_retry_delay=60.0)
        delay = limiter.get_retry_delay(HTTPStatus.TOO_MANY_REQUESTS, "300")
        assert delay == 60.0  # Capped at 60

    def test_get_retry_delay_ignores_header_when_disabled(self) -> None:
        """Test that Retry-After header is ignored when disabled."""
        limiter = RateLimiter(respect_retry_after=False, default_retry_delay=10.0)
        delay = limiter.get_retry_delay(HTTPStatus.TOO_MANY_REQUESTS, "30")
        assert delay == 10.0  # Uses default, not header value

    def test_get_retry_delay_handles_invalid_header(self) -> None:
        """Test that invalid Retry-After header falls back to default."""
        limiter = RateLimiter(default_retry_delay=20.0)
        delay = limiter.get_retry_delay(HTTPStatus.TOO_MANY_REQUESTS, "invalid")
        assert delay == 20.0


class TestRetryWithBackoff:
    """Test retry_with_backoff helper function."""

    async def test_succeeds_on_first_attempt(self) -> None:
        """Test that successful function returns immediately."""
        call_count = 0

        async def successful_func() -> str:
            nonlocal call_count
            call_count += 1
            return "success"

        result = await retry_with_backoff(successful_func)

        assert result == "success"
        assert call_count == 1

    async def test_retries_on_exception(self) -> None:
        """Test that function retries on exception."""
        call_count = 0

        async def failing_func() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("temporary failure")
            return "success"

        backoff = ExponentialBackoff(base_delay=0.01, max_retries=5)
        result = await retry_with_backoff(
            failing_func,
            backoff=backoff,
            retryable_exceptions=(ValueError,),
        )

        assert result == "success"
        assert call_count == 3

    async def test_exhausts_retries(self) -> None:
        """Test that all retries are exhausted before raising."""
        call_count = 0

        async def always_failing_func() -> str:
            nonlocal call_count
            call_count += 1
            raise ValueError("permanent failure")

        backoff = ExponentialBackoff(base_delay=0.01, max_retries=3)

        with pytest.raises(ValueError, match="permanent failure"):
            await retry_with_backoff(
                always_failing_func,
                backoff=backoff,
                retryable_exceptions=(ValueError,),
            )

        assert call_count == 3

    async def test_circuit_breaker_blocks_when_open(self) -> None:
        """Test that circuit breaker blocks execution when open."""
        breaker = CircuitBreaker(failure_threshold=2)

        # Open the circuit
        breaker.record_failure(Exception("test"))
        breaker.record_failure(Exception("test"))

        async def test_func() -> str:
            return "should not be called"

        with pytest.raises(RuntimeError, match="Circuit breaker is open"):
            await retry_with_backoff(test_func, circuit_breaker=breaker)

    async def test_circuit_breaker_records_success(self) -> None:
        """Test that circuit breaker records successes."""
        breaker = CircuitBreaker()

        async def successful_func() -> str:
            return "success"

        await retry_with_backoff(successful_func, circuit_breaker=breaker)

        # Success should be recorded (failure count should be 0)
        assert breaker.failure_count == 0

    async def test_circuit_breaker_records_failures(self) -> None:
        """Test that circuit breaker records failures."""
        breaker = CircuitBreaker(failure_threshold=10)

        async def failing_func() -> str:
            raise ValueError("test failure")

        backoff = ExponentialBackoff(base_delay=0.01, max_retries=3)

        with pytest.raises(ValueError):
            await retry_with_backoff(
                failing_func,
                circuit_breaker=breaker,
                backoff=backoff,
                retryable_exceptions=(ValueError,),
            )

        # Should have recorded 3 failures (one per attempt)
        assert breaker.failure_count == 3

    async def test_rate_limiter_waits_on_429(self) -> None:
        """Test that rate limiter causes wait on 429 response."""
        call_count = 0

        async def rate_limited_func() -> MagicMock:
            nonlocal call_count
            call_count += 1

            response = MagicMock()
            if call_count == 1:
                response.status = HTTPStatus.TOO_MANY_REQUESTS
                response.headers = {"Retry-After": "0.05"}
            else:
                response.status = HTTPStatus.OK
                response.headers = {}

            return response

        limiter = RateLimiter()
        backoff = ExponentialBackoff(base_delay=0.01, max_retries=5)

        result = await retry_with_backoff(
            rate_limited_func,
            backoff=backoff,
            rate_limiter=limiter,
            get_response_status=lambda r: r.status,
            get_retry_after=lambda r: r.headers.get("Retry-After"),
        )

        assert result.status == HTTPStatus.OK
        assert call_count == 2  # Should retry after rate limit

    async def test_only_retries_specified_exceptions(self) -> None:
        """Test that only specified exception types trigger retry."""
        call_count = 0

        async def mixed_exceptions_func() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("retryable")
            raise TypeError("not retryable")

        backoff = ExponentialBackoff(base_delay=0.01, max_retries=5)

        # Only retry ValueError
        with pytest.raises(TypeError, match="not retryable"):
            await retry_with_backoff(
                mixed_exceptions_func,
                backoff=backoff,
                retryable_exceptions=(ValueError,),
            )

        assert call_count == 2  # First attempt + one retry
