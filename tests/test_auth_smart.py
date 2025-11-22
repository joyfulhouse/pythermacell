"""Tests for smart authentication and ensure_authenticated behavior."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

from pythermacell.auth import AuthenticationHandler


if TYPE_CHECKING:
    from aiohttp import ClientSession


class TestAuthenticateForceParameter:
    """Test the force parameter in authenticate method."""

    async def test_authenticate_without_force_skips_if_valid(self, mock_session: ClientSession) -> None:
        """Test that authenticate without force skips if tokens are valid."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
            auth_lifetime_seconds=3600,
        )

        # First authentication
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
        assert mock_session.post.call_count == 1

        # Second call without force - should skip
        result = await handler.authenticate(force=False)
        assert result is True
        assert mock_session.post.call_count == 1  # Not called again

    async def test_authenticate_with_force_always_authenticates(self, mock_session: ClientSession) -> None:
        """Test that authenticate with force=True always authenticates."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
        )

        # First authentication
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
        assert mock_session.post.call_count == 1

        # Second call with force=True - should call again
        await handler.authenticate(force=True)
        assert mock_session.post.call_count == 2


class TestEnsureAuthenticated:
    """Test the ensure_authenticated method."""

    async def test_ensure_authenticated_on_first_call(self, mock_session: ClientSession) -> None:
        """Test that ensure_authenticated authenticates on first call."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
        )

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

        # Should authenticate
        await handler.ensure_authenticated()

        assert handler.is_authenticated() is True
        assert mock_session.post.call_count == 1

    async def test_ensure_authenticated_skips_if_valid(self, mock_session: ClientSession) -> None:
        """Test that ensure_authenticated skips if tokens are valid."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
            auth_lifetime_seconds=3600,
        )

        # First authentication
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

        await handler.ensure_authenticated()
        assert mock_session.post.call_count == 1

        # Second call - should not authenticate again
        await handler.ensure_authenticated()
        assert mock_session.post.call_count == 1  # Still 1

    async def test_ensure_authenticated_multiple_calls_efficient(self, mock_session: ClientSession) -> None:
        """Test that multiple ensure_authenticated calls are efficient."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
        )

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

        # Call ensure_authenticated 10 times
        for _ in range(10):
            await handler.ensure_authenticated()

        # Should only authenticate once
        assert mock_session.post.call_count == 1
        assert handler.is_authenticated() is True


class TestForceReauthenticate:
    """Test the force_reauthenticate method."""

    async def test_force_reauthenticate_always_authenticates(self, mock_session: ClientSession) -> None:
        """Test that force_reauthenticate always makes API call."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
        )

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

        # Initial authentication
        await handler.authenticate()
        assert mock_session.post.call_count == 1

        # Force reauthenticate should call again
        result = await handler.force_reauthenticate()

        assert result is True
        assert mock_session.post.call_count == 2

    async def test_force_reauthenticate_after_401_scenario(self, mock_session: ClientSession) -> None:
        """Test force_reauthenticate usage after receiving 401 from API."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
        )

        # Setup response
        mock_response = MagicMock()
        mock_response.status = HTTPStatus.OK
        mock_response.json = AsyncMock(
            return_value={
                "accesstoken": "new_token",
                "idtoken": "header.eyJjdXN0b206dXNlcl9pZCI6Im5ld3VzZXIifQ.sig",
            }
        )
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.post.return_value = mock_response

        # Simulate scenario: had old tokens, got 401, force reauth
        handler.access_token = "old_expired_token"
        handler.user_id = "olduser"

        # Force reauthenticate
        await handler.force_reauthenticate()

        # Should have new tokens
        assert handler.access_token == "new_token"
        assert handler.user_id == "newuser"


class TestSmartReauthenticationLifecycle:
    """Test complete lifecycle with smart reauthentication."""

    async def test_typical_usage_pattern(self, mock_session: ClientSession) -> None:
        """Test typical usage pattern with ensure_authenticated."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
            auth_lifetime_seconds=14400,  # 4 hours
        )

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

        # Simulate making multiple API calls
        for _ in range(5):
            await handler.ensure_authenticated()
            # ... make API call with handler.access_token

        # Should only authenticate once
        assert mock_session.post.call_count == 1

    async def test_usage_pattern_with_forced_reauth(self, mock_session: ClientSession) -> None:
        """Test usage pattern with forced reauth after 401."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
        )

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

        # Initial authentication
        await handler.ensure_authenticated()
        assert mock_session.post.call_count == 1

        # Make a few API calls
        await handler.ensure_authenticated()
        await handler.ensure_authenticated()
        assert mock_session.post.call_count == 1  # Still 1

        # Simulate receiving 401 from API
        # Application calls force_reauthenticate
        await handler.force_reauthenticate()
        assert mock_session.post.call_count == 2

        # Continue with API calls
        await handler.ensure_authenticated()
        await handler.ensure_authenticated()
        assert mock_session.post.call_count == 2  # Still 2
