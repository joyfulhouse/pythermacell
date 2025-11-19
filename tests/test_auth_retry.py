"""Tests for authentication retry logic on 401/403 errors."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from pythermacell.auth import AuthenticationHandler
from pythermacell.exceptions import AuthenticationError


if TYPE_CHECKING:
    from aiohttp import ClientSession


class TestShouldRetryOnStatus:
    """Test the should_retry_on_status helper method."""

    async def test_should_retry_on_401(self, mock_session: ClientSession) -> None:
        """Test that 401 status triggers retry."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
        )

        assert handler.should_retry_on_status(HTTPStatus.UNAUTHORIZED) is True

    async def test_should_retry_on_403(self, mock_session: ClientSession) -> None:
        """Test that 403 status triggers retry."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
        )

        assert handler.should_retry_on_status(HTTPStatus.FORBIDDEN) is True

    async def test_should_not_retry_on_200(self, mock_session: ClientSession) -> None:
        """Test that 200 status does not trigger retry."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
        )

        assert handler.should_retry_on_status(HTTPStatus.OK) is False

    async def test_should_not_retry_on_404(self, mock_session: ClientSession) -> None:
        """Test that 404 status does not trigger retry."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
        )

        assert handler.should_retry_on_status(HTTPStatus.NOT_FOUND) is False

    async def test_should_not_retry_on_500(self, mock_session: ClientSession) -> None:
        """Test that 500 status does not trigger retry."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
        )

        assert handler.should_retry_on_status(HTTPStatus.INTERNAL_SERVER_ERROR) is False


class TestHandleAuthRetry:
    """Test the handle_auth_retry method."""

    async def test_retry_on_401_succeeds(self, mock_session: ClientSession) -> None:
        """Test successful retry after 401 error."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
        )

        # Setup initial authentication
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

        await handler.authenticate()
        assert handler.access_token == "token123"

        # Simulate 401 error - should trigger reauthentication
        initial_call_count = mock_session.post.call_count

        # Mock new token after reauthentication
        mock_response2 = MagicMock()
        mock_response2.status = HTTPStatus.OK
        mock_response2.json = AsyncMock(
            return_value={
                "accesstoken": "new_token456",
                "idtoken": "header.eyJjdXN0b206dXNlcl9pZCI6InVzZXIxMjMifQ.sig",
            }
        )
        mock_response2.__aenter__ = AsyncMock(return_value=mock_response2)
        mock_response2.__aexit__ = AsyncMock(return_value=None)
        mock_session.post.return_value = mock_response2

        # Handle retry for 401
        await handler.handle_auth_retry(HTTPStatus.UNAUTHORIZED)

        # Should have reauthenticated
        assert mock_session.post.call_count == initial_call_count + 1
        assert handler.access_token == "new_token456"

    async def test_retry_on_403_succeeds(self, mock_session: ClientSession) -> None:
        """Test successful retry after 403 error."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
        )

        # Setup initial authentication
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

        await handler.authenticate()

        # Handle retry for 403
        await handler.handle_auth_retry(HTTPStatus.FORBIDDEN)

        # Should have reauthenticated
        assert mock_session.post.call_count == 2

    async def test_retry_raises_if_persistent_401(self, mock_session: ClientSession) -> None:
        """Test that persistent 401 after retry raises AuthenticationError."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
        )

        # Setup authentication to fail with 401
        mock_response = MagicMock()
        mock_response.status = HTTPStatus.UNAUTHORIZED
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.post.return_value = mock_response

        # Should raise AuthenticationError when retry fails
        with pytest.raises(
            AuthenticationError,
            match=r"Reauthentication failed after receiving status 401.*Credentials may be invalid",
        ):
            await handler.handle_auth_retry(HTTPStatus.UNAUTHORIZED)

    async def test_retry_raises_if_persistent_403(self, mock_session: ClientSession) -> None:
        """Test that persistent 403 after retry raises AuthenticationError."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
        )

        # Setup authentication to fail with 403
        mock_response = MagicMock()
        mock_response.status = HTTPStatus.FORBIDDEN
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.post.return_value = mock_response

        # Should raise AuthenticationError when retry fails
        with pytest.raises(
            AuthenticationError,
            match=r"Reauthentication failed after receiving status 403.*Credentials may be invalid",
        ):
            await handler.handle_auth_retry(HTTPStatus.FORBIDDEN)

    async def test_no_retry_on_200(self, mock_session: ClientSession) -> None:
        """Test that 200 status does not trigger retry."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
        )

        # Setup initial authentication
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

        await handler.authenticate()
        initial_call_count = mock_session.post.call_count

        # Handle 200 - should not retry
        await handler.handle_auth_retry(HTTPStatus.OK)

        # Should NOT have reauthenticated
        assert mock_session.post.call_count == initial_call_count


class TestAuthRetryIntegration:
    """Test complete retry workflow integration."""

    async def test_typical_retry_workflow(self, mock_session: ClientSession) -> None:
        """Test typical workflow: authenticate -> API call -> 401 -> retry -> success."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
        )

        # Initial authentication
        mock_response = MagicMock()
        mock_response.status = HTTPStatus.OK
        mock_response.json = AsyncMock(
            return_value={
                "accesstoken": "initial_token",
                "idtoken": "header.eyJjdXN0b206dXNlcl9pZCI6InVzZXIxMjMifQ.sig",
            }
        )
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.post.return_value = mock_response

        await handler.authenticate()
        assert handler.access_token == "initial_token"

        # Simulate API returning 401 (token expired on server)
        # Application detects 401 and calls handle_auth_retry

        # Setup reauthentication to succeed
        mock_response2 = MagicMock()
        mock_response2.status = HTTPStatus.OK
        mock_response2.json = AsyncMock(
            return_value={
                "accesstoken": "refreshed_token",
                "idtoken": "header.eyJjdXN0b206dXNlcl9pZCI6InVzZXIxMjMifQ.sig",
            }
        )
        mock_response2.__aenter__ = AsyncMock(return_value=mock_response2)
        mock_response2.__aexit__ = AsyncMock(return_value=None)
        mock_session.post.return_value = mock_response2

        await handler.handle_auth_retry(HTTPStatus.UNAUTHORIZED)
        assert handler.access_token == "refreshed_token"

        # Subsequent API calls should use new token
        assert handler.is_authenticated()
