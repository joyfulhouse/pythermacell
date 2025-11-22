"""Integration tests for resilience patterns with real API."""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import TYPE_CHECKING

import pytest
from aiohttp import ClientSession

from pythermacell import AuthenticationError, AuthenticationHandler, ThermacellClient
from pythermacell.resilience import CircuitBreaker, CircuitState, ExponentialBackoff, RateLimiter


if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def session() -> AsyncGenerator[ClientSession]:
    """Create aiohttp session for tests."""
    async with ClientSession() as sess:
        yield sess


class TestCircuitBreakerIntegration:
    """Integration tests for circuit breaker pattern with real API."""

    async def test_circuit_breaker_with_valid_requests(
        self, integration_config: dict[str, str], session: ClientSession
    ) -> None:
        """Test circuit breaker remains closed with successful requests."""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=10.0)

        client = ThermacellClient(
            username=integration_config["username"],
            password=integration_config["password"],
            base_url=integration_config["base_url"],
            session=session,
            circuit_breaker=breaker,
        )

        async with client:
            # Make several successful requests
            for _ in range(5):
                devices = await client.get_devices()
                assert isinstance(devices, list), "Request should succeed"

            # Circuit should remain closed
            assert breaker.state == CircuitState.CLOSED, "Circuit should be closed after successful requests"
            assert breaker.failure_count == 0, "Failure count should be 0"

    async def test_circuit_breaker_with_invalid_credentials(
        self, integration_config: dict[str, str], session: ClientSession
    ) -> None:
        """Test circuit breaker opens after consecutive authentication failures."""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=10.0)

        client = ThermacellClient(
            username="invalid@example.com",
            password="wrong_password",
            base_url=integration_config["base_url"],
            session=session,
            circuit_breaker=breaker,
        )

        async with client:
            # Make requests that will fail authentication
            for _ in range(3):
                with contextlib.suppress(AuthenticationError):
                    await client.get_devices()

            # Circuit should be open after threshold failures
            assert breaker.state == CircuitState.OPEN, "Circuit should be open after failures"
            assert breaker.failure_count >= 3, "Failure count should be at least 3"

    async def test_circuit_breaker_recovery(self, integration_config: dict[str, str], session: ClientSession) -> None:
        """Test circuit breaker can recover after timeout."""
        # Use short recovery timeout for testing
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=2.0, success_threshold=1)

        # First, cause circuit to open with invalid credentials
        bad_client = ThermacellClient(
            username="invalid@example.com",
            password="wrong_password",
            base_url=integration_config["base_url"],
            session=session,
            circuit_breaker=breaker,
        )

        async with bad_client:
            for _ in range(2):
                with contextlib.suppress(AuthenticationError):
                    await bad_client.get_devices()

        assert breaker.state == CircuitState.OPEN, "Circuit should be open"

        # Wait for recovery timeout
        await asyncio.sleep(3)

        # Circuit should transition to half-open
        assert breaker.state == CircuitState.HALF_OPEN, "Circuit should be half-open after timeout"

        # Now make successful request with valid credentials
        good_client = ThermacellClient(
            username=integration_config["username"],
            password=integration_config["password"],
            base_url=integration_config["base_url"],
            session=session,
            circuit_breaker=breaker,
        )

        async with good_client:
            devices = await good_client.get_devices()
            assert isinstance(devices, list), "Request should succeed"

            # Circuit should close after successful request in half-open
            assert breaker.state == CircuitState.CLOSED, "Circuit should close after success"


class TestExponentialBackoffIntegration:
    """Integration tests for exponential backoff with real API."""

    async def test_backoff_with_retry_on_auth_failure(
        self, integration_config: dict[str, str], session: ClientSession
    ) -> None:
        """Test exponential backoff retries authentication failures."""
        backoff = ExponentialBackoff(base_delay=0.5, max_delay=2.0, max_retries=3)

        client = ThermacellClient(
            username="invalid@example.com",
            password="wrong_password",
            base_url=integration_config["base_url"],
            session=session,
            backoff=backoff,
        )

        async with client:
            start_time = time.time()

            # This should retry 3 times with backoff
            with contextlib.suppress(AuthenticationError):
                await client.get_devices()

            elapsed = time.time() - start_time

            # Should have taken at least some time due to retries
            # With base_delay=0.5 and 3 retries, minimum time is ~1.5s
            # (0.5 + 1.0 + 1.5 with jitter reducing it)
            assert elapsed >= 0.5, "Should have taken time for retries"

    async def test_backoff_succeeds_with_valid_credentials(
        self, integration_config: dict[str, str], session: ClientSession
    ) -> None:
        """Test backoff pattern doesn't interfere with successful requests."""
        backoff = ExponentialBackoff(base_delay=0.5, max_delay=2.0, max_retries=3)

        client = ThermacellClient(
            username=integration_config["username"],
            password=integration_config["password"],
            base_url=integration_config["base_url"],
            session=session,
            backoff=backoff,
        )

        async with client:
            # Should succeed on first try without retries
            devices = await client.get_devices()
            assert isinstance(devices, list), "Request should succeed"


class TestRateLimiterIntegration:
    """Integration tests for rate limiter with real API."""

    async def test_rate_limiter_configuration(self, integration_config: dict[str, str], session: ClientSession) -> None:
        """Test rate limiter is properly configured."""
        rate_limiter = RateLimiter(respect_retry_after=True, default_retry_delay=30.0, max_retry_delay=120.0)

        client = ThermacellClient(
            username=integration_config["username"],
            password=integration_config["password"],
            base_url=integration_config["base_url"],
            session=session,
            rate_limiter=rate_limiter,
        )

        async with client:
            # Make normal request
            devices = await client.get_devices()
            assert isinstance(devices, list), "Request should succeed"

            # Rate limiter should not interfere with normal requests
            # (only activates on 429 responses)

    async def test_rate_limiter_delay_calculation(self) -> None:
        """Test rate limiter calculates delays correctly."""
        rate_limiter = RateLimiter(respect_retry_after=True, default_retry_delay=60.0, max_retry_delay=300.0)

        # Test with no Retry-After header
        delay = rate_limiter.get_retry_delay(429, None)
        assert delay == 60.0, "Should use default delay when no header"

        # Test with Retry-After header (seconds)
        delay = rate_limiter.get_retry_delay(429, "30")
        assert delay == 30.0, "Should parse Retry-After as seconds"

        # Test with Retry-After header exceeding max
        delay = rate_limiter.get_retry_delay(429, "500")
        assert delay == 300.0, "Should cap at max_retry_delay"

        # Test with non-429 status
        delay = rate_limiter.get_retry_delay(200, "30")
        assert delay == 0.0, "Should return 0 for non-429 status"


class TestCombinedResiliencePatterns:
    """Integration tests for combined resilience patterns."""

    async def test_all_resilience_patterns_together(
        self, integration_config: dict[str, str], session: ClientSession
    ) -> None:
        """Test all resilience patterns work together."""
        breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)
        backoff = ExponentialBackoff(base_delay=0.5, max_delay=5.0, max_retries=3)
        rate_limiter = RateLimiter(respect_retry_after=True, default_retry_delay=60.0)

        client = ThermacellClient(
            username=integration_config["username"],
            password=integration_config["password"],
            base_url=integration_config["base_url"],
            session=session,
            circuit_breaker=breaker,
            backoff=backoff,
            rate_limiter=rate_limiter,
        )

        async with client:
            # Make several successful requests
            for _ in range(3):
                devices = await client.get_devices()
                assert isinstance(devices, list), "Requests should succeed"

            # All patterns should allow successful requests through
            assert breaker.state == CircuitState.CLOSED, "Circuit should be closed"
            assert breaker.failure_count == 0, "No failures should be recorded"

    async def test_resilience_patterns_with_device_operations(
        self, integration_config: dict[str, str], session: ClientSession
    ) -> None:
        """Test resilience patterns work with device control operations."""
        breaker = CircuitBreaker(failure_threshold=5)
        backoff = ExponentialBackoff(max_retries=2)

        client = ThermacellClient(
            username=integration_config["username"],
            password=integration_config["password"],
            base_url=integration_config["base_url"],
            session=session,
            circuit_breaker=breaker,
            backoff=backoff,
        )

        async with client:
            devices = await client.get_devices()

            if len(devices) > 0:
                device = devices[0]

                # Device operations should work with resilience patterns
                # Verify device has state
                assert device._state is not None, "Device should have state"

                # Test refresh works with resilience
                success = await device.refresh()
                assert success is True, "Refresh should succeed"

                # Circuit should remain closed
                assert breaker.state == CircuitState.CLOSED, "Circuit should be closed"


class TestResilienceWithAuthentication:
    """Integration tests for resilience patterns with authentication."""

    async def test_circuit_breaker_with_auth_handler(
        self, integration_config: dict[str, str], session: ClientSession
    ) -> None:
        """Test circuit breaker works with authentication handler."""
        breaker = CircuitBreaker(failure_threshold=3)
        backoff = ExponentialBackoff(max_retries=2)

        handler = AuthenticationHandler(
            username=integration_config["username"],
            password=integration_config["password"],
            base_url=integration_config["base_url"],
            session=session,
            circuit_breaker=breaker,
            backoff=backoff,
        )

        async with handler:
            # Authentication should succeed
            success = await handler.authenticate()
            assert success, "Authentication should succeed"

            # Circuit should be closed after success
            assert breaker.state == CircuitState.CLOSED, "Circuit should be closed"
            assert breaker.failure_count == 0, "No failures should be recorded"

    async def test_backoff_with_auth_retry(self, integration_config: dict[str, str], session: ClientSession) -> None:
        """Test exponential backoff with authentication retries."""
        backoff = ExponentialBackoff(base_delay=0.5, max_retries=2)

        handler = AuthenticationHandler(
            username=integration_config["username"],
            password=integration_config["password"],
            base_url=integration_config["base_url"],
            session=session,
            backoff=backoff,
        )

        async with handler:
            # Should succeed on first try (no retries needed)
            success = await handler.authenticate()
            assert success, "Authentication should succeed"


class TestResilienceEdgeCases:
    """Integration tests for resilience pattern edge cases."""

    async def test_circuit_breaker_reset(self, integration_config: dict[str, str], session: ClientSession) -> None:
        """Test circuit breaker can be manually reset."""
        breaker = CircuitBreaker(failure_threshold=2)

        # Cause failures to open circuit
        bad_client = ThermacellClient(
            username="invalid@example.com",
            password="wrong_password",
            base_url=integration_config["base_url"],
            session=session,
            circuit_breaker=breaker,
        )

        async with bad_client:
            for _ in range(2):
                with contextlib.suppress(AuthenticationError):
                    await bad_client.get_devices()

        assert breaker.state == CircuitState.OPEN, "Circuit should be open"

        # Manually reset
        breaker.reset()

        assert breaker.state == CircuitState.CLOSED, "Circuit should be closed after reset"
        assert breaker.failure_count == 0, "Failure count should be 0 after reset"

    async def test_backoff_delay_progression(self) -> None:
        """Test exponential backoff delay progression."""
        backoff = ExponentialBackoff(base_delay=1.0, exponential_base=2.0, max_delay=60.0, jitter=False)

        # Test delay progression
        delay0 = backoff.calculate_delay(0)
        delay1 = backoff.calculate_delay(1)
        delay2 = backoff.calculate_delay(2)
        delay3 = backoff.calculate_delay(3)

        # Without jitter, delays should be: 1, 2, 4, 8
        assert delay0 == 1.0, "First delay should be base_delay"
        assert delay1 == 2.0, "Second delay should be base_delay * 2"
        assert delay2 == 4.0, "Third delay should be base_delay * 4"
        assert delay3 == 8.0, "Fourth delay should be base_delay * 8"

    async def test_backoff_with_jitter_variation(self) -> None:
        """Test exponential backoff jitter adds randomness."""
        backoff = ExponentialBackoff(base_delay=10.0, jitter=True)

        # Calculate same delay multiple times
        delays = [backoff.calculate_delay(1) for _ in range(10)]

        # With jitter, delays should vary
        unique_delays = set(delays)
        assert len(unique_delays) > 1, "Jitter should produce different delays"

        # All delays should be less than or equal to max calculated delay
        max_calculated = 10.0 * 2.0  # base * exponential_base^1
        assert all(d <= max_calculated for d in delays), "All delays should be within bounds"
