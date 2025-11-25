"""Authentication handler for Thermacell API."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import UTC, datetime
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from pythermacell.const import (
    BASE64_PADDING_MODULO,
    DEFAULT_AUTH_LIFETIME_SECONDS,
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT,
    JWT_PARTS_COUNT,
)
from pythermacell.exceptions import AuthenticationError, ThermacellConnectionError, ThermacellTimeoutError


if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

    from pythermacell.resilience import CircuitBreaker, ExponentialBackoff, RateLimiter

_LOGGER = logging.getLogger(__name__)


class AuthenticationHandler:
    """Handle authentication with the Thermacell ESP RainMaker API.

    This class manages JWT-based authentication, token storage, session
    management, and automatic reauthentication for the Thermacell API.

    Session Update Callback:
        When an injected session is provided and authentication succeeds,
        the on_session_updated callback will be invoked with the handler instance.
        This allows the client application to retrieve updated tokens:

        Example:
            def handle_session_update(handler: AuthenticationHandler) -> None:
                # Store updated tokens for future use
                my_app.access_token = handler.access_token
                my_app.user_id = handler.user_id

            handler = AuthenticationHandler(
                username="user@example.com",
                password="password",
                session=my_session,
                on_session_updated=handle_session_update
            )

    Attributes:
        username: User's email address for authentication.
        password: User's password for authentication.
        base_url: Base URL for the API (without trailing slash).
        access_token: JWT access token for API requests (None if not authenticated).
        user_id: User ID extracted from the ID token (None if not authenticated).
        last_authenticated_at: Timestamp of last successful authentication (None if never authenticated).
    """

    def __init__(
        self,
        username: str,
        password: str,
        base_url: str = DEFAULT_BASE_URL,
        *,
        session: ClientSession | None = None,
        on_session_updated: Callable[[AuthenticationHandler], None] | None = None,
        auth_lifetime_seconds: int = DEFAULT_AUTH_LIFETIME_SECONDS,
        circuit_breaker: CircuitBreaker | None = None,
        backoff: ExponentialBackoff | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        """Initialize the authentication handler.

        Args:
            username: User's email address.
            password: User's password.
            base_url: Base URL for the API. Defaults to Thermacell production API.
            session: Optional aiohttp ClientSession. If not provided, one will be
                created when entering the context manager. When a session is injected,
                automatic authentication does NOT occur - you must call authenticate()
                manually.
            on_session_updated: Optional callback invoked when authentication succeeds.
                Receives the handler instance with updated tokens. Use this to
                synchronize token state when using an injected session.
            auth_lifetime_seconds: Estimated lifetime of auth tokens in seconds.
                Defaults to 14400 (4 hours). Used to determine when reauthentication
                may be needed. This is conservative - actual tokens may last longer.
            circuit_breaker: Optional CircuitBreaker for fault tolerance. If provided,
                authentication attempts will be blocked when the circuit is open.
            backoff: Optional ExponentialBackoff for retry delays. If provided,
                failed authentication attempts will retry with exponential backoff.
            rate_limiter: Optional RateLimiter for handling 429 responses. If provided,
                will respect Retry-After headers from the API.
        """
        self.username = username
        self.password = password
        self.base_url = base_url.rstrip("/")
        self.access_token: str | None = None
        self.user_id: str | None = None
        self.last_authenticated_at: datetime | None = None

        self._session = session
        self._owns_session = session is None
        self._auth_lock = asyncio.Lock()
        self._on_session_updated = on_session_updated
        self._auth_lifetime_seconds = auth_lifetime_seconds
        self._circuit_breaker = circuit_breaker
        self._backoff = backoff
        self._rate_limiter = rate_limiter

    def set_session(self, session: ClientSession) -> None:
        """Set the aiohttp session for this handler.

        This should be called by the client managing the session lifecycle.
        The handler will not take ownership and will not close this session.

        Args:
            session: The aiohttp ClientSession to use for requests.
        """
        self._session = session
        self._owns_session = False

    async def __aenter__(self) -> AuthenticationHandler:
        """Enter the context manager.

        Creates a new aiohttp session if one wasn't provided during initialization.

        Returns:
            Self for use in async with statements.
        """
        if self._session is None:
            self._session = ClientSession()
            self._owns_session = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the context manager.

        Closes the session if it was created by this handler.

        Args:
            exc_type: Exception type if an exception occurred.
            exc_val: Exception value if an exception occurred.
            exc_tb: Exception traceback if an exception occurred.
        """
        if self._owns_session and self._session is not None:
            await self._session.close()

    def is_authenticated(self) -> bool:
        """Check if the handler has valid authentication tokens.

        Returns:
            True if both access_token and user_id are set, False otherwise.
        """
        return self.access_token is not None and self.user_id is not None

    def _validate_session(self) -> None:
        """Validate that the session is initialized and open.

        Raises:
            RuntimeError: If session is not initialized or is closed.
        """
        if self._session is None:
            msg = "Session not initialized. Use 'async with' or provide a session."
            raise RuntimeError(msg)

        if self._session.closed:
            msg = "Session is closed. Cannot make requests."
            raise RuntimeError(msg)

    def _decode_jwt_payload(self, jwt_token: str) -> dict[str, Any]:
        """Decode JWT token payload without verification.

        Args:
            jwt_token: JWT token string in format header.payload.signature.

        Returns:
            Dictionary containing the decoded payload, or empty dict if decoding fails.
        """
        try:
            parts = jwt_token.split(".")
            if len(parts) != JWT_PARTS_COUNT:
                _LOGGER.debug(
                    "Invalid JWT format: expected %d parts, got %d",
                    JWT_PARTS_COUNT,
                    len(parts),
                )
                return {}

            payload = parts[1]

            # Add base64 padding if needed
            padding = BASE64_PADDING_MODULO - len(payload) % BASE64_PADDING_MODULO
            if padding != BASE64_PADDING_MODULO:
                payload += "=" * padding

            decoded_bytes = base64.urlsafe_b64decode(payload)
            decoded_payload: dict[str, Any] = json.loads(decoded_bytes.decode("utf-8"))
        except (ValueError, KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            _LOGGER.debug("Failed to decode JWT payload: %s", exc)
            return {}
        else:
            return decoded_payload

    async def authenticate(self, *, force: bool = False) -> bool:
        """Authenticate with the Thermacell API using username and password.

        This method performs the following:
        1. Makes a POST request to /v1/login2 with credentials
        2. Extracts the access token from the response
        3. Decodes the ID token to extract the user ID
        4. Stores both tokens for future API requests

        When resilience patterns are enabled:
        - Circuit breaker will block requests when open
        - Exponential backoff will retry failed attempts with delays
        - Rate limiter will respect 429 Retry-After headers

        Args:
            force: If True, always authenticate even if tokens appear valid.
                If False (default), skip authentication if already authenticated
                and tokens haven't expired.

        Returns:
            True if authentication was successful.

        Raises:
            AuthenticationError: If authentication fails (invalid credentials,
                missing tokens, etc.).
            TimeoutError: If the request times out.
            ConnectionError: If a connection error occurs.
            RuntimeError: If circuit breaker is open.
        """
        self._validate_session()

        # Skip authentication if not forced and we have valid tokens
        if not force and self.is_authenticated() and not self.needs_reauthentication():
            _LOGGER.debug("Skipping authentication - valid tokens already exist")
            return True

        # Check circuit breaker before attempting
        if self._circuit_breaker is not None and not self._circuit_breaker.can_execute():
            msg = "Circuit breaker is open - authentication requests are blocked"
            raise RuntimeError(msg)

        async with self._auth_lock:
            # Determine max retries from backoff config
            max_attempts = 1
            if self._backoff is not None:
                max_attempts = self._backoff.max_retries

            last_exception: Exception | None = None

            for attempt in range(max_attempts):
                try:
                    result = await self._authenticate_attempt()

                    # Record success with circuit breaker
                    if self._circuit_breaker is not None:
                        self._circuit_breaker.record_success()

                    return result

                except (AuthenticationError, ThermacellTimeoutError, ThermacellConnectionError) as exc:
                    last_exception = exc

                    # Record failure with circuit breaker
                    if self._circuit_breaker is not None:
                        self._circuit_breaker.record_failure(exc)

                    # Check if we should retry
                    if attempt < max_attempts - 1:
                        # Calculate delay using backoff
                        if self._backoff is not None:
                            delay = self._backoff.calculate_delay(attempt)
                            _LOGGER.warning(
                                "Authentication attempt %d failed, retrying in %.2fs: %s",
                                attempt + 1,
                                delay,
                                exc,
                            )
                            await asyncio.sleep(delay)
                        else:
                            _LOGGER.warning("Authentication attempt %d failed: %s", attempt + 1, exc)
                    else:
                        _LOGGER.exception("Authentication failed after %d attempts", max_attempts)

            # All retries exhausted
            if last_exception is not None:
                raise last_exception

            # Should never reach here, but satisfy type checker
            msg = "Authentication failed for unknown reason"
            raise AuthenticationError(msg)

    async def _authenticate_attempt(self) -> bool:
        """Perform a single authentication attempt.

        This is a helper method that performs the actual HTTP request and token extraction.
        It's separated from authenticate() to enable retry logic.

        Returns:
            True if authentication was successful.

        Raises:
            AuthenticationError: If authentication fails.
            ThermacellTimeoutError: If the request times out.
            ThermacellConnectionError: If a connection error occurs.
        """
        try:
            url = f"{self.base_url}/v1/login2"
            data = {
                "user_name": self.username,
                "password": self.password,
            }

            timeout = ClientTimeout(total=DEFAULT_TIMEOUT)

            _LOGGER.debug("Authenticating with %s", url)

            # Session should be validated by authenticate(), but double-check
            self._validate_session()
            # We know _session is not None after validation
            assert self._session is not None

            async with self._session.post(url, json=data, timeout=timeout) as response:
                # Handle rate limiting
                if response.status == HTTPStatus.TOO_MANY_REQUESTS and self._rate_limiter is not None:
                    retry_after = response.headers.get("Retry-After")
                    delay = self._rate_limiter.get_retry_delay(response.status, retry_after)
                    _LOGGER.warning("Rate limited, waiting %.2fs before retry", delay)
                    await asyncio.sleep(delay)
                    msg = f"Rate limited (status {response.status})"
                    raise AuthenticationError(msg)

                if response.status == HTTPStatus.UNAUTHORIZED:
                    msg = "Authentication failed: Invalid credentials"
                    raise AuthenticationError(msg)

                if response.status != HTTPStatus.OK:
                    msg = f"Authentication failed with status {response.status}"
                    raise AuthenticationError(msg)

                auth_data = await response.json()

                # Extract access token
                self.access_token = auth_data.get("accesstoken")
                if not self.access_token:
                    msg = "Missing access token in authentication response"
                    raise AuthenticationError(msg)

                # Extract user ID from ID token
                id_token = auth_data.get("idtoken")
                if id_token:
                    id_payload = self._decode_jwt_payload(id_token)
                    if id_payload:
                        self.user_id = id_payload.get("custom:user_id")

                if not self.user_id:
                    msg = "Failed to extract user ID from token"
                    raise AuthenticationError(msg)

                # Track when authentication occurred
                self.last_authenticated_at = datetime.now(UTC)

                _LOGGER.info("Authentication successful for user %s", self.user_id)

                # Invoke callback if provided (for session update notification)
                if self._on_session_updated is not None:
                    self._on_session_updated(self)

                return True

        except TimeoutError as exc:
            msg = "Authentication request timed out"
            raise ThermacellTimeoutError(msg) from exc

        except ClientError as exc:
            msg = f"Failed to connect to API: {exc}"
            raise ThermacellConnectionError(msg) from exc

        except json.JSONDecodeError as exc:
            msg = f"Invalid JSON response from API: {exc}"
            raise AuthenticationError(msg) from exc

    async def ensure_authenticated(self) -> None:
        """Ensure valid authentication, only reauthenticating if necessary.

        This is the recommended method to call before making API requests.
        It intelligently determines whether reauthentication is needed based on:
        - Whether tokens exist
        - Whether tokens have expired (based on configured lifetime)

        This method will NOT reauthenticate if valid tokens already exist,
        reducing unnecessary API calls and improving performance.

        Use this instead of calling authenticate() directly in most cases.

        Raises:
            AuthenticationError: If authentication fails.
            TimeoutError: If the request times out.
            ConnectionError: If a connection error occurs.
        """
        await self.authenticate(force=False)

    async def force_reauthenticate(self) -> bool:
        """Force reauthentication even if tokens appear valid.

        Useful when you know the tokens have been invalidated (e.g., after
        receiving a 401 Unauthorized response from an API call).

        Returns:
            True if authentication was successful.

        Raises:
            AuthenticationError: If authentication fails.
            TimeoutError: If the request times out.
            ConnectionError: If a connection error occurs.
        """
        _LOGGER.info("Forcing reauthentication")
        return await self.authenticate(force=True)

    def needs_reauthentication(self) -> bool:
        """Check if reauthentication may be needed.

        This method checks if the handler has never been authenticated or if the
        authentication timestamp suggests the tokens may have expired.

        Returns:
            True if reauthentication may be needed, False otherwise.
        """
        if not self.is_authenticated():
            return True

        if self.last_authenticated_at is None:
            return True

        # Check if auth is older than the configured lifetime
        time_since_auth = (datetime.now(UTC) - self.last_authenticated_at).total_seconds()
        return time_since_auth >= self._auth_lifetime_seconds

    def clear_authentication(self) -> None:
        """Clear all authentication state.

        This removes stored tokens and resets authentication tracking.
        Useful when explicitly logging out or when you want to force
        reauthentication on the next API call.
        """
        self.access_token = None
        self.user_id = None
        self.last_authenticated_at = None
        _LOGGER.debug("Authentication state cleared")

    def should_retry_on_status(self, status_code: int) -> bool:
        """Check if a status code should trigger authentication retry.

        Args:
            status_code: HTTP status code from API response.

        Returns:
            True if the status code indicates authentication should be retried
            (401 Unauthorized or 403 Forbidden), False otherwise.
        """
        return status_code in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN)

    async def handle_auth_retry(self, status_code: int) -> None:
        """Handle authentication retry for 401/403 errors.

        This method should be called when an API request returns 401 or 403.
        It will force reauthentication if the status code indicates auth failure.
        If reauthentication fails, it raises AuthenticationError.

        Args:
            status_code: HTTP status code that triggered the retry.

        Raises:
            AuthenticationError: If reauthentication fails or status indicates
                persistent authentication failure.

        Example:
            response = await session.get(url, headers={"Authorization": auth.access_token})
            if auth.should_retry_on_status(response.status):
                await auth.handle_auth_retry(response.status)
                # Retry the request with new token
                response = await session.get(url, headers={"Authorization": auth.access_token})
        """
        if not self.should_retry_on_status(status_code):
            # No retry needed for this status code
            return

        _LOGGER.warning(
            "Received status %d, attempting reauthentication",
            status_code,
        )

        # Force reauthentication
        try:
            await self.force_reauthenticate()
        except AuthenticationError:
            # Reauthentication failed - credentials are invalid
            msg = f"Reauthentication failed after receiving status {status_code}. Credentials may be invalid."
            raise AuthenticationError(msg) from None
