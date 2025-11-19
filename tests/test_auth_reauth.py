"""Tests for authentication reauthentication and session handling."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from pythermacell.auth import AuthenticationHandler
from pythermacell.exceptions import AuthenticationError


if TYPE_CHECKING:
    from aiohttp import ClientSession


class TestSessionInjectionBehavior:
    """Test that injected sessions don't auto-authenticate."""

    async def test_injected_session_no_auto_authenticate(self, mock_session: ClientSession) -> None:
        """Test that providing a session doesn't trigger automatic authentication."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
        )

        # Verify no authentication occurred during initialization
        mock_session.post.assert_not_called()
        assert handler.access_token is None
        assert handler.user_id is None

    async def test_manual_authenticate_with_injected_session(self, mock_session: ClientSession) -> None:
        """Test that manual authentication works with injected session."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
        )

        # Setup mock response
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

        # Manual authentication should work
        success = await handler.authenticate()

        assert success is True
        assert handler.access_token == "token123"
        assert handler.user_id == "user123"


class TestReauthenticationOnExpiry:
    """Test reauthentication when sessions expire."""

    async def test_authenticate_updates_expiry_tracking(self, mock_session: ClientSession) -> None:
        """Test that successful authentication tracks when it occurred."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
        )

        # Setup mock response
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

        # Before auth
        assert handler.last_authenticated_at is None

        await handler.authenticate()

        # After auth
        assert handler.last_authenticated_at is not None

    async def test_reauthenticate_clears_old_tokens(self, mock_session: ClientSession) -> None:
        """Test that reauthentication replaces old tokens."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
        )

        # First authentication
        mock_response1 = MagicMock()
        mock_response1.status = HTTPStatus.OK
        mock_response1.json = AsyncMock(
            return_value={
                "accesstoken": "old_token",
                "idtoken": "header.eyJjdXN0b206dXNlcl9pZCI6Im9sZHVzZXIifQ.sig",
            }
        )
        mock_response1.__aenter__ = AsyncMock(return_value=mock_response1)
        mock_response1.__aexit__ = AsyncMock(return_value=None)
        mock_session.post.return_value = mock_response1

        await handler.authenticate()
        assert handler.access_token == "old_token"
        assert handler.user_id == "olduser"

        # Second authentication (reauthentication) - must use force=True to reauthenticate
        mock_response2 = MagicMock()
        mock_response2.status = HTTPStatus.OK
        mock_response2.json = AsyncMock(
            return_value={
                "accesstoken": "new_token",
                "idtoken": "header.eyJjdXN0b206dXNlcl9pZCI6Im5ld3VzZXIifQ.sig",
            }
        )
        mock_response2.__aenter__ = AsyncMock(return_value=mock_response2)
        mock_response2.__aexit__ = AsyncMock(return_value=None)
        mock_session.post.return_value = mock_response2

        await handler.authenticate(force=True)
        assert handler.access_token == "new_token"
        assert handler.user_id == "newuser"


class TestSessionUpdateCallback:
    """Test session update callback mechanism."""

    async def test_callback_invoked_on_successful_auth(self, mock_session: ClientSession) -> None:
        """Test that callback is invoked when authentication succeeds."""
        callback_invoked = False
        received_handler = None

        def session_updated(handler: AuthenticationHandler) -> None:
            nonlocal callback_invoked, received_handler
            callback_invoked = True
            received_handler = handler

        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
            on_session_updated=session_updated,
        )

        # Setup mock response
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

        assert callback_invoked is True
        assert received_handler is handler
        assert received_handler.access_token == "token123"

    async def test_callback_not_invoked_on_auth_failure(self, mock_session: ClientSession) -> None:
        """Test that callback is not invoked when authentication fails."""
        callback_invoked = False

        def session_updated(handler: AuthenticationHandler) -> None:
            nonlocal callback_invoked
            callback_invoked = True

        handler = AuthenticationHandler(
            username="test@example.com",
            password="wrong_password",
            session=mock_session,
            on_session_updated=session_updated,
        )

        # Setup mock 401 response
        mock_response = MagicMock()
        mock_response.status = HTTPStatus.UNAUTHORIZED
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.post.return_value = mock_response

        with pytest.raises(AuthenticationError):
            await handler.authenticate()

        assert callback_invoked is False

    async def test_callback_invoked_on_reauthentication(self, mock_session: ClientSession) -> None:
        """Test that callback is invoked on each reauthentication."""
        callback_count = 0

        def session_updated(handler: AuthenticationHandler) -> None:
            nonlocal callback_count
            callback_count += 1

        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
            on_session_updated=session_updated,
        )

        # Setup mock response for both auths
        mock_response = MagicMock()
        mock_response.status = HTTPStatus.OK
        mock_response.json = AsyncMock(
            return_value={
                "accesstoken": "token",
                "idtoken": "header.eyJjdXN0b206dXNlcl9pZCI6InVzZXIifQ.sig",
            }
        )
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.post.return_value = mock_response

        # First authentication
        await handler.authenticate()
        assert callback_count == 1

        # Second authentication - must use force=True to reauthenticate
        await handler.authenticate(force=True)
        assert callback_count == 2


class TestAuthenticationHelpers:
    """Test helper methods for authentication state."""

    async def test_needs_reauthentication_no_auth(self) -> None:
        """Test needs_reauthentication returns True when never authenticated."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
        )

        assert handler.needs_reauthentication() is True

    async def test_needs_reauthentication_after_auth(self, mock_session: ClientSession) -> None:
        """Test needs_reauthentication returns False immediately after auth."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
        )

        # Setup mock response
        mock_response = MagicMock()
        mock_response.status = HTTPStatus.OK
        mock_response.json = AsyncMock(
            return_value={
                "accesstoken": "token",
                "idtoken": "header.eyJjdXN0b206dXNlcl9pZCI6InVzZXIifQ.sig",
            }
        )
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.post.return_value = mock_response

        await handler.authenticate()

        # Should not need reauth immediately
        assert handler.needs_reauthentication() is False

    async def test_clear_authentication_state(self, mock_session: ClientSession) -> None:
        """Test that clear_authentication removes tokens and tracking."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
        )

        # Authenticate first
        mock_response = MagicMock()
        mock_response.status = HTTPStatus.OK
        mock_response.json = AsyncMock(
            return_value={
                "accesstoken": "token",
                "idtoken": "header.eyJjdXN0b206dXNlcl9pZCI6InVzZXIifQ.sig",
            }
        )
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.post.return_value = mock_response

        await handler.authenticate()
        assert handler.is_authenticated() is True

        # Clear authentication
        handler.clear_authentication()

        assert handler.access_token is None
        assert handler.user_id is None
        assert handler.last_authenticated_at is None
        assert handler.is_authenticated() is False
