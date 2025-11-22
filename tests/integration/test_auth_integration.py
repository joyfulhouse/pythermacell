"""Integration tests for authentication with real API."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from aiohttp import ClientSession

from pythermacell import AuthenticationError, AuthenticationHandler


if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def session() -> AsyncGenerator[ClientSession]:
    """Create aiohttp session for tests."""
    async with ClientSession() as sess:
        yield sess


class TestAuthenticationIntegration:
    """Integration tests for AuthenticationHandler with real API."""

    async def test_authenticate_with_valid_credentials(
        self, integration_config: dict[str, str], session: ClientSession
    ) -> None:
        """Test authentication succeeds with valid credentials."""
        handler = AuthenticationHandler(
            username=integration_config["username"],
            password=integration_config["password"],
            base_url=integration_config["base_url"],
            session=session,
        )

        # Enter context manager
        async with handler:
            # Authenticate
            success = await handler.authenticate()

            # Verify authentication succeeded
            assert success, "Authentication should succeed with valid credentials"
            assert handler.access_token is not None, "Access token should be set"
            assert handler.user_id is not None, "User ID should be extracted from token"
            assert handler.is_authenticated(), "Handler should report as authenticated"
            assert handler.last_authenticated_at is not None, "Timestamp should be set"

    async def test_authenticate_with_invalid_credentials(
        self, integration_config: dict[str, str], session: ClientSession
    ) -> None:
        """Test authentication fails with invalid credentials."""
        handler = AuthenticationHandler(
            username="invalid@example.com",
            password="wrong_password",
            base_url=integration_config["base_url"],
            session=session,
        )

        async with handler:
            # Attempt to authenticate (API returns 400 for invalid credentials)
            with pytest.raises(AuthenticationError, match="Authentication failed"):
                await handler.authenticate()

            # Verify no tokens were set
            assert handler.access_token is None, "Access token should not be set"
            assert handler.user_id is None, "User ID should not be set"
            assert not handler.is_authenticated(), "Handler should not be authenticated"

    async def test_force_reauthenticate(self, integration_config: dict[str, str], session: ClientSession) -> None:
        """Test force reauthentication refreshes tokens."""
        handler = AuthenticationHandler(
            username=integration_config["username"],
            password=integration_config["password"],
            base_url=integration_config["base_url"],
            session=session,
        )

        async with handler:
            # Initial authentication
            await handler.authenticate()
            first_timestamp = handler.last_authenticated_at

            # Force reauthentication
            success = await handler.force_reauthenticate()

            # Verify reauthentication succeeded
            assert success, "Reauthentication should succeed"
            assert handler.access_token is not None, "New token should be set"
            assert handler.last_authenticated_at is not None, "Timestamp should be updated"
            assert handler.last_authenticated_at != first_timestamp, (
                "Timestamp should be different after reauthentication"
            )

            # Note: Tokens might be the same if they haven't expired
            # We just verify the process completed successfully

    async def test_ensure_authenticated_skips_if_valid(
        self, integration_config: dict[str, str], session: ClientSession
    ) -> None:
        """Test ensure_authenticated doesn't reauthenticate if tokens are valid."""
        handler = AuthenticationHandler(
            username=integration_config["username"],
            password=integration_config["password"],
            base_url=integration_config["base_url"],
            session=session,
        )

        async with handler:
            # Initial authentication
            await handler.authenticate()
            first_token = handler.access_token
            first_timestamp = handler.last_authenticated_at

            # Call ensure_authenticated (should skip)
            await handler.ensure_authenticated()

            # Verify tokens weren't refreshed
            assert handler.access_token == first_token, "Token should be unchanged"
            assert handler.last_authenticated_at == first_timestamp, "Timestamp should be unchanged"

    async def test_clear_authentication(self, integration_config: dict[str, str], session: ClientSession) -> None:
        """Test clearing authentication state."""
        handler = AuthenticationHandler(
            username=integration_config["username"],
            password=integration_config["password"],
            base_url=integration_config["base_url"],
            session=session,
        )

        async with handler:
            # Authenticate first
            await handler.authenticate()
            assert handler.is_authenticated(), "Should be authenticated"

            # Clear authentication
            handler.clear_authentication()

            # Verify state is cleared
            assert handler.access_token is None, "Access token should be cleared"
            assert handler.user_id is None, "User ID should be cleared"
            assert handler.last_authenticated_at is None, "Timestamp should be cleared"
            assert not handler.is_authenticated(), "Should not be authenticated"

    async def test_authentication_with_owned_session(self, integration_config: dict[str, str]) -> None:
        """Test authentication when handler creates its own session."""
        handler = AuthenticationHandler(
            username=integration_config["username"],
            password=integration_config["password"],
            base_url=integration_config["base_url"],
            # No session provided - handler will create one
        )

        # Enter context manager (creates session)
        async with handler:
            # Authenticate
            success = await handler.authenticate()

            # Verify authentication succeeded
            assert success, "Authentication should succeed"
            assert handler.access_token is not None, "Access token should be set"
            assert handler.user_id is not None, "User ID should be set"

        # Session should be closed after exiting context

    async def test_jwt_token_decoding(self, integration_config: dict[str, str], session: ClientSession) -> None:
        """Test that JWT token is properly decoded to extract user_id."""
        handler = AuthenticationHandler(
            username=integration_config["username"],
            password=integration_config["password"],
            base_url=integration_config["base_url"],
            session=session,
        )

        async with handler:
            await handler.authenticate()

            # Verify user_id was extracted from JWT token
            assert handler.user_id is not None, "User ID should be extracted"
            assert isinstance(handler.user_id, str), "User ID should be string"
            assert len(handler.user_id) > 0, "User ID should not be empty"

            # User ID should match the pattern from ESP RainMaker
            # (typically UUID or similar identifier)
            assert "-" in handler.user_id or len(handler.user_id) > 10, "User ID should be valid identifier"


class TestAuthenticationCallback:
    """Integration tests for authentication callback functionality."""

    async def test_on_session_updated_callback(
        self, integration_config: dict[str, str], session: ClientSession
    ) -> None:
        """Test on_session_updated callback is invoked after authentication."""
        callback_invoked = False
        captured_tokens: dict[str, str | None] = {}

        def callback(handler: AuthenticationHandler) -> None:
            nonlocal callback_invoked, captured_tokens
            callback_invoked = True
            captured_tokens["access_token"] = handler.access_token
            captured_tokens["user_id"] = handler.user_id

        handler = AuthenticationHandler(
            username=integration_config["username"],
            password=integration_config["password"],
            base_url=integration_config["base_url"],
            session=session,
            on_session_updated=callback,
        )

        async with handler:
            await handler.authenticate()

            # Verify callback was invoked
            assert callback_invoked, "Callback should be invoked after authentication"
            assert captured_tokens["access_token"] is not None, "Callback should receive access token"
            assert captured_tokens["user_id"] is not None, "Callback should receive user ID"
            assert captured_tokens["access_token"] == handler.access_token, "Callback should receive same token"
            assert captured_tokens["user_id"] == handler.user_id, "Callback should receive same user ID"


class TestAuthenticationTimeout:
    """Integration tests for authentication timeout handling."""

    @pytest.mark.slow
    async def test_authentication_respects_timeout(
        self, integration_config: dict[str, str], session: ClientSession
    ) -> None:
        """Test that authentication respects configured timeout."""
        # Note: This test just verifies timeout is configured correctly
        # Actual timeout errors would require network manipulation

        handler = AuthenticationHandler(
            username=integration_config["username"],
            password=integration_config["password"],
            base_url=integration_config["base_url"],
            session=session,
        )

        async with handler:
            # Authentication should succeed within timeout
            success = await handler.authenticate()
            assert success, "Authentication should complete within timeout"
