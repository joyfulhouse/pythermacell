"""Tests for pythermacell authentication handler."""

from __future__ import annotations

import builtins
from http import HTTPStatus
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientError

from pythermacell.auth import AuthenticationHandler
from pythermacell.exceptions import AuthenticationError, ThermacellConnectionError, ThermacellTimeoutError


if TYPE_CHECKING:
    from aiohttp import ClientSession


class TestAuthenticationHandlerInit:
    """Test AuthenticationHandler initialization."""

    async def test_init_with_username_password(self) -> None:
        """Test initialization with username and password."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
        )
        assert handler.username == "test@example.com"
        assert handler.password == "password123"
        assert handler.base_url == "https://api.iot.thermacell.com"
        assert handler.access_token is None
        assert handler.user_id is None

    async def test_init_with_custom_base_url(self) -> None:
        """Test initialization with custom base URL."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            base_url="https://custom.api.com/",
        )
        assert handler.base_url == "https://custom.api.com"  # Trailing slash removed

    async def test_init_with_session(self, mock_session: ClientSession) -> None:
        """Test initialization with provided session."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
        )
        assert handler._session == mock_session
        assert handler._owns_session is False

    async def test_init_without_session(self) -> None:
        """Test initialization creates session if not provided."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
        )
        assert handler._session is None
        assert handler._owns_session is True


class TestJWTDecoding:
    """Test JWT token decoding."""

    async def test_decode_valid_jwt(self) -> None:
        """Test decoding a valid JWT token."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
        )

        # Valid JWT with custom:user_id in payload
        token = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJjdXN0b206dXNlcl9pZCI6InVzZXIxMjMiLCJleHAiOjE3MzAwMDAwMDB9."
            "signature"
        )

        payload = handler._decode_jwt_payload(token)
        assert payload["custom:user_id"] == "user123"

    async def test_decode_jwt_with_padding(self) -> None:
        """Test decoding JWT that needs base64 padding."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
        )

        # Token that requires padding
        token = "header.eyJjdXN0b206dXNlcl9pZCI6InRlc3QifQ.signature"
        payload = handler._decode_jwt_payload(token)
        assert payload["custom:user_id"] == "test"

    async def test_decode_invalid_jwt_format(self) -> None:
        """Test decoding JWT with invalid format."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
        )

        # Invalid JWT (not 3 parts)
        token = "invalid.token"
        payload = handler._decode_jwt_payload(token)
        assert payload == {}

    async def test_decode_invalid_jwt_base64(self) -> None:
        """Test decoding JWT with invalid base64."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
        )

        # Invalid base64 content
        token = "header.!!!invalid_base64!!!.signature"
        payload = handler._decode_jwt_payload(token)
        assert payload == {}


class TestAuthentication:
    """Test authentication flow."""

    async def test_authenticate_success(self, mock_session: ClientSession) -> None:
        """Test successful authentication."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
        )

        # Mock successful response
        mock_response = MagicMock()
        mock_response.status = HTTPStatus.OK
        mock_response.json = AsyncMock(
            return_value={
                "accesstoken": "access_token_123",
                "idtoken": ("header.eyJjdXN0b206dXNlcl9pZCI6InVzZXIxMjMifQ.signature"),
            }
        )
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session.post.return_value = mock_response

        success = await handler.authenticate()

        assert success is True
        assert handler.access_token == "access_token_123"
        assert handler.user_id == "user123"

        # Verify correct API call
        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        assert call_args[0][0] == "https://api.iot.thermacell.com/v1/login2"
        assert call_args[1]["json"] == {
            "user_name": "test@example.com",
            "password": "password123",
        }

    async def test_authenticate_invalid_credentials(self, mock_session: ClientSession) -> None:
        """Test authentication with invalid credentials."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="wrong_password",
            session=mock_session,
        )

        # Mock 401 response
        mock_response = MagicMock()
        mock_response.status = HTTPStatus.UNAUTHORIZED
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.post.return_value = mock_response

        with pytest.raises(AuthenticationError, match="Authentication failed"):
            await handler.authenticate()

    async def test_authenticate_missing_access_token(self, mock_session: ClientSession) -> None:
        """Test authentication with missing access token in response."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
        )

        # Mock response without access token
        mock_response = MagicMock()
        mock_response.status = HTTPStatus.OK
        mock_response.json = AsyncMock(return_value={"idtoken": "token"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session.post.return_value = mock_response

        with pytest.raises(AuthenticationError, match="Missing access token"):
            await handler.authenticate()

    async def test_authenticate_timeout(self, mock_session: ClientSession) -> None:
        """Test authentication timeout."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
        )

        # Mock timeout - need to make the context manager raise the exception
        async def timeout_side_effect(*args: object, **kwargs: object) -> None:
            raise builtins.TimeoutError

        mock_response = MagicMock()
        mock_response.__aenter__ = timeout_side_effect
        mock_session.post.return_value = mock_response

        with pytest.raises(ThermacellTimeoutError, match="Authentication request timed out"):
            await handler.authenticate()

    async def test_authenticate_connection_error(self, mock_session: ClientSession) -> None:
        """Test authentication connection error."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
        )

        # Mock connection error - need to make the context manager raise the exception
        async def connection_error_side_effect(*args: object, **kwargs: object) -> None:
            msg = "Connection failed"
            raise ClientError(msg)

        mock_response = MagicMock()
        mock_response.__aenter__ = connection_error_side_effect
        mock_session.post.return_value = mock_response

        with pytest.raises(ThermacellConnectionError, match="Failed to connect"):
            await handler.authenticate()

    async def test_authenticate_with_lock(self, mock_session: ClientSession) -> None:
        """Test that authentication uses lock for thread safety."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
        )

        # Mock successful response
        mock_response = MagicMock()
        mock_response.status = HTTPStatus.OK
        mock_response.json = AsyncMock(
            return_value={
                "accesstoken": "token",
                "idtoken": "header.eyJjdXN0b206dXNlcl9pZCI6InRlc3QifQ.sig",
            }
        )
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.post.return_value = mock_response

        # Patch the lock to verify it's used
        with patch.object(handler._auth_lock, "acquire", wraps=handler._auth_lock.acquire) as mock_acquire:
            await handler.authenticate()
            mock_acquire.assert_called_once()


class TestContextManager:
    """Test context manager functionality."""

    async def test_context_manager_creates_session(self) -> None:
        """Test context manager creates session when not provided."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
        )

        async with handler as h:
            assert h._session is not None
            assert h._owns_session is True

    async def test_context_manager_closes_owned_session(self) -> None:
        """Test context manager closes session it created."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
        )

        async with handler:
            session = handler._session
            assert session is not None
            assert not session.closed

        # Session should be closed after context exit
        assert session.closed

    async def test_context_manager_does_not_close_provided_session(self, mock_session: ClientSession) -> None:
        """Test context manager doesn't close provided session."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
            session=mock_session,
        )

        async with handler:
            assert handler._session == mock_session

        # Mock session should not be closed
        assert not mock_session.closed


class TestIsAuthenticated:
    """Test authentication status checking."""

    async def test_is_authenticated_true(self) -> None:
        """Test is_authenticated returns True when tokens are set."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
        )
        handler.access_token = "token"
        handler.user_id = "user123"

        assert handler.is_authenticated() is True

    async def test_is_authenticated_false_no_token(self) -> None:
        """Test is_authenticated returns False without access token."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
        )
        handler.user_id = "user123"

        assert handler.is_authenticated() is False

    async def test_is_authenticated_false_no_user_id(self) -> None:
        """Test is_authenticated returns False without user ID."""
        handler = AuthenticationHandler(
            username="test@example.com",
            password="password123",
        )
        handler.access_token = "token"

        assert handler.is_authenticated() is False


# Import asyncio at module level for the test
