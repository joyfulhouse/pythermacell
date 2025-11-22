"""Tests for authentication resilience pattern integration."""

from __future__ import annotations

import asyncio
from http import HTTPStatus
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from pythermacell.auth import AuthenticationHandler
from pythermacell.exceptions import AuthenticationError
from pythermacell.resilience import CircuitBreaker, ExponentialBackoff, RateLimiter


if TYPE_CHECKING:
    from aiohttp import ClientSession


class TestCircuitBreakerIntegration:
    """Test circuit breaker integration in authentication."""

    async def test_circuit_breaker_blocks_when_open(self, mock_session: ClientSession) -> None:
        """Test that circuit breaker blocks authentication when open."""
        breaker = CircuitBreaker(failure_threshold=2)
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
            circuit_breaker=breaker,
        )

        # Open the circuit by recording failures
        breaker.record_failure(Exception("test"))
        breaker.record_failure(Exception("test"))
        assert breaker.state.value == "open"

        # Attempt authentication - should be blocked
        with pytest.raises(RuntimeError, match="Circuit breaker is open"):
            await handler.authenticate()

    async def test_circuit_breaker_records_success(self, mock_session: ClientSession) -> None:
        """Test that successful authentication records success with circuit breaker."""
        breaker = CircuitBreaker()
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
            circuit_breaker=breaker,
        )

        # Setup successful response
        mock_response = MagicMock()
        mock_response.status = HTTPStatus.OK
        mock_response.json = AsyncMock(
            return_value={
                "accesstoken": "token123",
                "idtoken": "header.eyJjdXN0b206dXNlcl9pZCI6InVzZXIxMjMifQ.sig",
            }
        )
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.post.return_value = mock_response

        # Authenticate
        await handler.authenticate()

        # Circuit breaker should have recorded success
        assert breaker.failure_count == 0

    async def test_circuit_breaker_records_failures(self, mock_session: ClientSession) -> None:
        """Test that failed authentication records failures with circuit breaker."""
        breaker = CircuitBreaker(failure_threshold=10)
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
            circuit_breaker=breaker,
        )

        # Setup failed response
        mock_response = MagicMock()
        mock_response.status = HTTPStatus.UNAUTHORIZED
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.post.return_value = mock_response

        # Attempt authentication
        with pytest.raises(AuthenticationError):
            await handler.authenticate()

        # Circuit breaker should have recorded failure
        assert breaker.failure_count == 1


class TestExponentialBackoffIntegration:
    """Test exponential backoff integration in authentication."""

    async def test_backoff_retries_on_failure(self, mock_session: ClientSession) -> None:
        """Test that failed authentication retries with exponential backoff."""
        backoff = ExponentialBackoff(base_delay=0.01, max_retries=3)
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
            backoff=backoff,
        )

        call_count = 0

        def create_response() -> MagicMock:
            nonlocal call_count
            call_count += 1

            mock_response = MagicMock()
            if call_count < 3:
                # First 2 attempts fail
                mock_response.status = HTTPStatus.INTERNAL_SERVER_ERROR
            else:
                # Third attempt succeeds
                mock_response.status = HTTPStatus.OK
                mock_response.json = AsyncMock(
                    return_value={
                        "accesstoken": "token123",
                        "idtoken": "header.eyJjdXN0b206dXNlcl9pZCI6InVzZXIxMjMifQ.sig",
                    }
                )

            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)
            return mock_response

        mock_session.post.side_effect = lambda *args, **kwargs: create_response()

        # Authenticate - should retry and eventually succeed
        result = await handler.authenticate()

        assert result is True
        assert call_count == 3

    async def test_backoff_exhausts_retries(self, mock_session: ClientSession) -> None:
        """Test that backoff exhausts all retries before failing."""
        backoff = ExponentialBackoff(base_delay=0.01, max_retries=3)
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
            backoff=backoff,
        )

        # Setup always-failing response
        mock_response = MagicMock()
        mock_response.status = HTTPStatus.UNAUTHORIZED
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.post.return_value = mock_response

        # Attempt authentication - should fail after retries
        with pytest.raises(AuthenticationError, match="Invalid credentials"):
            await handler.authenticate()

        # Should have attempted 3 times
        assert mock_session.post.call_count == 3

    async def test_backoff_no_retry_without_backoff(self, mock_session: ClientSession) -> None:
        """Test that without backoff, no retry occurs."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
            # No backoff configured
        )

        # Setup failing response
        mock_response = MagicMock()
        mock_response.status = HTTPStatus.UNAUTHORIZED
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.post.return_value = mock_response

        # Attempt authentication - should fail immediately
        with pytest.raises(AuthenticationError):
            await handler.authenticate()

        # Should only attempt once
        assert mock_session.post.call_count == 1


class TestRateLimiterIntegration:
    """Test rate limiter integration in authentication."""

    async def test_rate_limiter_handles_429(self, mock_session: ClientSession) -> None:
        """Test that rate limiter handles 429 responses."""
        rate_limiter = RateLimiter()
        backoff = ExponentialBackoff(base_delay=0.01, max_retries=2)
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
            backoff=backoff,
            rate_limiter=rate_limiter,
        )

        call_count = 0

        def create_response() -> MagicMock:
            nonlocal call_count
            call_count += 1

            mock_response = MagicMock()
            if call_count == 1:
                # First attempt: rate limited
                mock_response.status = HTTPStatus.TOO_MANY_REQUESTS
                mock_response.headers = {"Retry-After": "0.05"}
            else:
                # Second attempt: success
                mock_response.status = HTTPStatus.OK
                mock_response.json = AsyncMock(
                    return_value={
                        "accesstoken": "token123",
                        "idtoken": "header.eyJjdXN0b206dXNlcl9pZCI6InVzZXIxMjMifQ.sig",
                    }
                )
                mock_response.headers = {}

            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)
            return mock_response

        mock_session.post.side_effect = lambda *args, **kwargs: create_response()

        # Authenticate - should handle rate limit and retry
        result = await handler.authenticate()

        assert result is True
        assert call_count == 2

    async def test_rate_limiter_without_retry_after_header(self, mock_session: ClientSession) -> None:
        """Test rate limiter with no Retry-After header."""
        rate_limiter = RateLimiter(default_retry_delay=0.05)
        backoff = ExponentialBackoff(base_delay=0.01, max_retries=2)
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
            backoff=backoff,
            rate_limiter=rate_limiter,
        )

        call_count = 0

        def create_response() -> MagicMock:
            nonlocal call_count
            call_count += 1

            mock_response = MagicMock()
            if call_count == 1:
                # First attempt: rate limited without header
                mock_response.status = HTTPStatus.TOO_MANY_REQUESTS
                mock_response.headers = {}
            else:
                # Second attempt: success
                mock_response.status = HTTPStatus.OK
                mock_response.json = AsyncMock(
                    return_value={
                        "accesstoken": "token123",
                        "idtoken": "header.eyJjdXN0b206dXNlcl9pZCI6InVzZXIxMjMifQ.sig",
                    }
                )
                mock_response.headers = {}

            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)
            return mock_response

        mock_session.post.side_effect = lambda *args, **kwargs: create_response()

        # Authenticate - should use default delay
        result = await handler.authenticate()

        assert result is True
        assert call_count == 2


class TestCombinedResiliencePatterns:
    """Test combination of multiple resilience patterns."""

    async def test_all_patterns_together(self, mock_session: ClientSession) -> None:
        """Test using circuit breaker, backoff, and rate limiter together."""
        breaker = CircuitBreaker(failure_threshold=5)
        backoff = ExponentialBackoff(base_delay=0.01, max_retries=3)
        rate_limiter = RateLimiter()

        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
            circuit_breaker=breaker,
            backoff=backoff,
            rate_limiter=rate_limiter,
        )

        call_count = 0

        def create_response() -> MagicMock:
            nonlocal call_count
            call_count += 1

            mock_response = MagicMock()
            if call_count == 1:
                # First: rate limited
                mock_response.status = HTTPStatus.TOO_MANY_REQUESTS
                mock_response.headers = {"Retry-After": "0.01"}
            elif call_count == 2:
                # Second: server error
                mock_response.status = HTTPStatus.INTERNAL_SERVER_ERROR
                mock_response.headers = {}
            else:
                # Third: success
                mock_response.status = HTTPStatus.OK
                mock_response.json = AsyncMock(
                    return_value={
                        "accesstoken": "token123",
                        "idtoken": "header.eyJjdXN0b206dXNlcl9pZCI6InVzZXIxMjMifQ.sig",
                    }
                )
                mock_response.headers = {}

            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)
            return mock_response

        mock_session.post.side_effect = lambda *args, **kwargs: create_response()

        # Authenticate with all patterns
        result = await handler.authenticate()

        assert result is True
        assert call_count == 3
        # Circuit breaker should have recorded both failures and final success
        assert breaker.failure_count == 0  # Reset on success

    async def test_circuit_breaker_opens_with_backoff(self, mock_session: ClientSession) -> None:
        """Test that circuit breaker opens after exhausting retries."""
        breaker = CircuitBreaker(failure_threshold=2)
        backoff = ExponentialBackoff(base_delay=0.01, max_retries=5)

        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
            circuit_breaker=breaker,
            backoff=backoff,
        )

        # Setup always-failing response
        mock_response = MagicMock()
        mock_response.status = HTTPStatus.UNAUTHORIZED
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.post.return_value = mock_response

        # First authentication attempt - should fail and record failures
        with pytest.raises(AuthenticationError):
            await handler.authenticate()

        # Circuit should be open now (failures recorded during retries)
        assert breaker.state.value == "open"

        # Second authentication attempt - should be blocked immediately
        with pytest.raises(RuntimeError, match="Circuit breaker is open"):
            await handler.authenticate()

        # First attempt made max_retries attempts, second was blocked
        assert mock_session.post.call_count == 5  # Only from first attempt

    async def test_backoff_with_circuit_breaker_half_open(self, mock_session: ClientSession) -> None:
        """Test backoff behavior when circuit breaker is in half-open state."""
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1, success_threshold=1)
        backoff = ExponentialBackoff(base_delay=0.01, max_retries=2)

        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
            circuit_breaker=breaker,
            backoff=backoff,
        )

        # Open the circuit
        mock_response_fail = MagicMock()
        mock_response_fail.status = HTTPStatus.UNAUTHORIZED
        mock_response_fail.__aenter__ = AsyncMock(return_value=mock_response_fail)
        mock_response_fail.__aexit__ = AsyncMock(return_value=None)
        mock_session.post.return_value = mock_response_fail

        with pytest.raises(AuthenticationError):
            await handler.authenticate()

        assert breaker.state.value == "open"

        # Wait for recovery timeout
        await asyncio.sleep(0.15)
        assert breaker.state.value == "half_open"

        # Setup successful response
        mock_response_success = MagicMock()
        mock_response_success.status = HTTPStatus.OK
        mock_response_success.json = AsyncMock(
            return_value={
                "accesstoken": "token123",
                "idtoken": "header.eyJjdXN0b206dXNlcl9pZCI6InVzZXIxMjMifQ.sig",
            }
        )
        mock_response_success.__aenter__ = AsyncMock(return_value=mock_response_success)
        mock_response_success.__aexit__ = AsyncMock(return_value=None)
        mock_session.post.return_value = mock_response_success

        # Should succeed and close circuit
        result = await handler.authenticate()

        assert result is True
        assert breaker.state.value == "closed"
