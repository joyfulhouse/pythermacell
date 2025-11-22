"""Resilience patterns for API clients (circuit breaker, exponential backoff, rate limiting)."""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from http import HTTPStatus
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

_LOGGER = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failures exceeded threshold, blocking requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker pattern.

    Attributes:
        failure_threshold: Number of consecutive failures before opening circuit.
        recovery_timeout: Seconds to wait before attempting recovery (half-open state).
        success_threshold: Number of consecutive successes in half-open to close circuit.
        monitored_exceptions: Exception types to count as failures.
    """

    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    success_threshold: int = 2
    monitored_exceptions: tuple[type[Exception], ...] = (Exception,)


@dataclass
class ExponentialBackoffConfig:
    """Configuration for exponential backoff pattern.

    Attributes:
        base_delay: Initial delay in seconds (default 1.0).
        max_delay: Maximum delay in seconds (default 60.0).
        max_retries: Maximum number of retry attempts (default 5).
        exponential_base: Multiplier for exponential growth (default 2.0).
        jitter: Add randomness to prevent thundering herd (default True).
    """

    base_delay: float = 1.0
    max_delay: float = 60.0
    max_retries: int = 5
    exponential_base: float = 2.0
    jitter: bool = True


@dataclass
class RateLimitConfig:
    """Configuration for rate limit handling.

    Attributes:
        respect_retry_after: Parse and respect Retry-After header (default True).
        default_retry_delay: Default delay when no Retry-After header (default 60.0).
        max_retry_delay: Maximum time to wait for rate limit (default 300.0 = 5 minutes).
    """

    respect_retry_after: bool = True
    default_retry_delay: float = 60.0
    max_retry_delay: float = 300.0


class CircuitBreaker:
    """Circuit breaker pattern implementation for fault tolerance.

    Prevents cascading failures by monitoring operation failures and temporarily
    blocking requests when failure threshold is exceeded.

    States:
        CLOSED: Normal operation, requests allowed
        OPEN: Failures exceeded threshold, requests blocked
        HALF_OPEN: Testing recovery, limited requests allowed

    Example:
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30.0)

        async def make_api_call():
            if not breaker.can_execute():
                raise Exception("Circuit breaker is open")

            try:
                result = await api.call()
                breaker.record_success()
                return result
            except Exception as e:
                breaker.record_failure(e)
                raise
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        success_threshold: int = 2,
        monitored_exceptions: tuple[type[Exception], ...] = (Exception,),
    ) -> None:
        """Initialize circuit breaker.

        Args:
            failure_threshold: Consecutive failures before opening circuit.
            recovery_timeout: Seconds before attempting recovery.
            success_threshold: Consecutive successes to close circuit from half-open.
            monitored_exceptions: Exception types to monitor.
        """
        self.config = CircuitBreakerConfig(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            success_threshold=success_threshold,
            monitored_exceptions=monitored_exceptions,
        )
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: datetime | None = None
        self._opened_at: datetime | None = None

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        self._update_state()
        return self._state

    @property
    def failure_count(self) -> int:
        """Get current failure count."""
        return self._failure_count

    @property
    def success_count(self) -> int:
        """Get current success count in half-open state."""
        return self._success_count

    def _update_state(self) -> None:
        """Update circuit state based on recovery timeout."""
        if self._state == CircuitState.OPEN and self._opened_at is not None:
            time_open = (datetime.now(UTC) - self._opened_at).total_seconds()
            if time_open >= self.config.recovery_timeout:
                _LOGGER.info("Circuit breaker entering HALF_OPEN state for recovery test")
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0

    def can_execute(self) -> bool:
        """Check if requests are allowed in current state.

        Returns:
            True if requests are allowed, False if circuit is open.
        """
        self._update_state()
        return self._state != CircuitState.OPEN

    def record_success(self) -> None:
        """Record a successful operation."""
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            _LOGGER.debug(
                "Circuit breaker recorded success in HALF_OPEN (%d/%d)",
                self._success_count,
                self.config.success_threshold,
            )

            if self._success_count >= self.config.success_threshold:
                _LOGGER.info("Circuit breaker closing after successful recovery")
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._success_count = 0
                self._opened_at = None
        elif self._state == CircuitState.CLOSED:
            # Reset failure count on success
            if self._failure_count > 0:
                _LOGGER.debug("Circuit breaker resetting failure count after success")
                self._failure_count = 0

    def record_failure(self, exception: Exception) -> None:
        """Record a failed operation.

        Args:
            exception: The exception that occurred.
        """
        # Only count monitored exception types
        if not isinstance(exception, self.config.monitored_exceptions):
            return

        self._last_failure_time = datetime.now(UTC)

        if self._state == CircuitState.HALF_OPEN:
            # Any failure in half-open immediately opens circuit
            _LOGGER.warning("Circuit breaker opening after failure in HALF_OPEN state")
            self._state = CircuitState.OPEN
            self._opened_at = datetime.now(UTC)
            self._failure_count += 1
            self._success_count = 0

        elif self._state == CircuitState.CLOSED:
            self._failure_count += 1
            _LOGGER.debug("Circuit breaker failure count: %d/%d", self._failure_count, self.config.failure_threshold)

            if self._failure_count >= self.config.failure_threshold:
                _LOGGER.warning(
                    "Circuit breaker opening after %d consecutive failures",
                    self._failure_count,
                )
                self._state = CircuitState.OPEN
                self._opened_at = datetime.now(UTC)

    def reset(self) -> None:
        """Reset circuit breaker to closed state."""
        _LOGGER.info("Circuit breaker manually reset")
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._opened_at = None
        self._last_failure_time = None


class ExponentialBackoff:
    """Exponential backoff calculator for retry delays.

    Calculates progressively longer delays between retries with optional jitter
    to prevent thundering herd problem.

    Example:
        backoff = ExponentialBackoff(base_delay=1.0, max_delay=60.0, max_retries=5)

        for attempt in range(backoff.max_retries):
            try:
                return await make_request()
            except Exception:
                if attempt < backoff.max_retries - 1:
                    delay = backoff.calculate_delay(attempt)
                    await asyncio.sleep(delay)
                else:
                    raise
    """

    def __init__(
        self,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        max_retries: int = 5,
        exponential_base: float = 2.0,
        *,
        jitter: bool = True,
    ) -> None:
        """Initialize exponential backoff calculator.

        Args:
            base_delay: Initial delay in seconds.
            max_delay: Maximum delay in seconds.
            max_retries: Maximum number of retry attempts.
            exponential_base: Multiplier for exponential growth.
            jitter: Add randomness to delays (prevents thundering herd).
        """
        self.config = ExponentialBackoffConfig(
            base_delay=base_delay,
            max_delay=max_delay,
            max_retries=max_retries,
            exponential_base=exponential_base,
            jitter=jitter,
        )

    @property
    def max_retries(self) -> int:
        """Get maximum number of retries."""
        return self.config.max_retries

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for a given retry attempt.

        Args:
            attempt: Retry attempt number (0-indexed).

        Returns:
            Delay in seconds for this attempt.
        """
        # Calculate exponential delay: base_delay * (exponential_base ^ attempt)
        delay = self.config.base_delay * (self.config.exponential_base**attempt)

        # Cap at max_delay
        delay = min(delay, self.config.max_delay)

        # Add jitter if enabled: random value between 0 and delay
        if self.config.jitter:
            delay = random.uniform(0, delay)  # noqa: S311

        return delay


class RateLimiter:
    """Rate limit handler with Retry-After header support.

    Handles HTTP 429 (Too Many Requests) responses by parsing Retry-After
    headers and calculating appropriate wait times.

    Example:
        limiter = RateLimiter()

        response = await session.get(url)
        if response.status == 429:
            delay = limiter.get_retry_delay(response)
            await asyncio.sleep(delay)
            response = await session.get(url)  # Retry
    """

    def __init__(
        self,
        respect_retry_after: bool = True,
        default_retry_delay: float = 60.0,
        max_retry_delay: float = 300.0,
    ) -> None:
        """Initialize rate limiter.

        Args:
            respect_retry_after: Parse and respect Retry-After header.
            default_retry_delay: Default delay when no Retry-After header.
            max_retry_delay: Maximum time to wait (safety limit).
        """
        self.config = RateLimitConfig(
            respect_retry_after=respect_retry_after,
            default_retry_delay=default_retry_delay,
            max_retry_delay=max_retry_delay,
        )

    def get_retry_delay(self, response_status: int, retry_after_header: str | None = None) -> float:
        """Calculate retry delay from response.

        Args:
            response_status: HTTP status code.
            retry_after_header: Value of Retry-After header (if present).

        Returns:
            Delay in seconds before retrying.
        """
        if response_status != HTTPStatus.TOO_MANY_REQUESTS:
            return 0.0

        if not self.config.respect_retry_after or not retry_after_header:
            return self.config.default_retry_delay

        # Try to parse Retry-After header
        # Can be either seconds (integer) or HTTP date
        try:
            # Try parsing as integer (seconds)
            delay = float(retry_after_header)
            _LOGGER.debug("Parsed Retry-After as %f seconds", delay)
        except ValueError:
            # Try parsing as HTTP date (not commonly used)
            _LOGGER.debug("Could not parse Retry-After header, using default delay")
            delay = self.config.default_retry_delay

        # Cap at max_retry_delay for safety
        return min(delay, self.config.max_retry_delay)

    @staticmethod
    def is_rate_limited(status_code: int) -> bool:
        """Check if status code indicates rate limiting.

        Args:
            status_code: HTTP status code.

        Returns:
            True if status indicates rate limiting.
        """
        return status_code == HTTPStatus.TOO_MANY_REQUESTS


async def retry_with_backoff(
    func: Callable[[], Awaitable[Any]],
    *,
    circuit_breaker: CircuitBreaker | None = None,
    backoff: ExponentialBackoff | None = None,
    rate_limiter: RateLimiter | None = None,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    get_response_status: Callable[[Any], int] | None = None,
    get_retry_after: Callable[[Any], str | None] | None = None,
) -> Any:
    """Execute function with retry, backoff, circuit breaker, and rate limiting.

    This is a comprehensive retry helper that combines all resilience patterns:
    - Circuit breaker: Prevents cascading failures
    - Exponential backoff: Progressive retry delays
    - Rate limiting: Respects 429 responses and Retry-After headers

    Args:
        func: Async function to execute.
        circuit_breaker: Optional circuit breaker instance.
        backoff: Optional exponential backoff instance.
        rate_limiter: Optional rate limiter instance.
        retryable_exceptions: Exception types that should trigger retry.
        get_response_status: Function to extract HTTP status from result.
        get_retry_after: Function to extract Retry-After header from result.

    Returns:
        Result from func() if successful.

    Raises:
        Exception: Re-raises last exception if all retries exhausted.
        RuntimeError: If circuit breaker is open.

    Example:
        breaker = CircuitBreaker(failure_threshold=3)
        backoff = ExponentialBackoff(max_retries=5)
        limiter = RateLimiter()

        async def make_request():
            response = await session.get(url)
            return response

        result = await retry_with_backoff(
            make_request,
            circuit_breaker=breaker,
            backoff=backoff,
            rate_limiter=limiter,
            get_response_status=lambda r: r.status,
            get_retry_after=lambda r: r.headers.get("Retry-After"),
        )
    """
    # Use default backoff if none provided
    if backoff is None:
        backoff = ExponentialBackoff()

    last_exception: Exception | None = None

    for attempt in range(backoff.max_retries):
        # Check circuit breaker before attempt
        if circuit_breaker and not circuit_breaker.can_execute():
            msg = f"Circuit breaker is {circuit_breaker.state.value}, blocking request"
            raise RuntimeError(msg)

        try:
            result = await func()

            # Check for rate limiting
            if rate_limiter and get_response_status:
                status = get_response_status(result)

                if rate_limiter.is_rate_limited(status):
                    retry_after = get_retry_after(result) if get_retry_after else None
                    delay = rate_limiter.get_retry_delay(status, retry_after)

                    _LOGGER.warning(
                        "Rate limited (429), waiting %.1f seconds before retry",
                        delay,
                    )

                    await asyncio.sleep(delay)

                    # Don't count rate limiting as a failure
                    if circuit_breaker:
                        circuit_breaker.record_success()

                    continue  # Retry immediately after rate limit delay

            # Success - record in circuit breaker
            if circuit_breaker:
                circuit_breaker.record_success()

            return result
        except retryable_exceptions as exc:
            last_exception = exc

            # Record failure in circuit breaker
            if circuit_breaker:
                circuit_breaker.record_failure(exc)

            # Check if we should retry
            if attempt < backoff.max_retries - 1:
                delay = backoff.calculate_delay(attempt)
                _LOGGER.warning(
                    "Attempt %d/%d failed: %s. Retrying in %.1f seconds",
                    attempt + 1,
                    backoff.max_retries,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
            else:
                _LOGGER.exception(
                    "All %d retry attempts exhausted",
                    backoff.max_retries,
                )
                raise

    # Should not reach here, but raise last exception if we do
    if last_exception:
        raise last_exception

    msg = "Unexpected state: no result and no exception"
    raise RuntimeError(msg)
