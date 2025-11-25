"""Low-level API client for Thermacell ESP RainMaker endpoints.

This module provides direct HTTP communication with the Thermacell API.
All methods return (status_code, response_data) tuples for maximum flexibility.
"""

from __future__ import annotations

import asyncio
import logging
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from pythermacell.const import DEFAULT_BASE_URL, DEFAULT_TIMEOUT


# Maximum number of rate-limit retries to prevent infinite recursion
MAX_RATE_LIMIT_RETRIES = 3

if TYPE_CHECKING:
    from types import TracebackType

    from pythermacell.auth import AuthenticationHandler
    from pythermacell.resilience import CircuitBreaker, ExponentialBackoff, RateLimiter

_LOGGER = logging.getLogger(__name__)


class ThermacellAPI:
    """Low-level API client for Thermacell ESP RainMaker platform.

    This class handles raw HTTP communication with the Thermacell API,
    including request construction, authentication headers, and response parsing.

    All methods return (status_code, response_data) tuples to allow callers
    to implement their own error handling and retry logic.

    Example:
        ```python
        from aiohttp import ClientSession
        from pythermacell.api import ThermacellAPI
        from pythermacell.auth import AuthenticationHandler

        async with ClientSession() as session:
            auth = AuthenticationHandler(
                username="user@example.com", password="pass", session=session
            )
            api = ThermacellAPI(auth_handler=auth, session=session)

            async with api:
                # Discover devices
                status, data = await api.get_nodes()
                if status == 200:
                    node_ids = data.get("nodes", [])

                # Get device state
                status, params = await api.get_node_params(node_ids[0])

                # Control device
                status, _ = await api.update_node_params(
                    node_ids[0], {"LIV Hub": {"Enable Repellers": True}}
                )
        ```

    Attributes:
        base_url: Base URL for the API (default: https://api.iot.thermacell.com).
    """

    def __init__(
        self,
        *,
        auth_handler: AuthenticationHandler,
        session: ClientSession | None = None,
        base_url: str = DEFAULT_BASE_URL,
        circuit_breaker: CircuitBreaker | None = None,
        backoff: ExponentialBackoff | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        """Initialize the API client.

        Args:
            auth_handler: AuthenticationHandler for managing tokens.
            session: Optional aiohttp ClientSession. If not provided, one will be
                created when entering the context manager.
            base_url: Base URL for the API. Defaults to Thermacell production API.
            circuit_breaker: Optional CircuitBreaker for fault tolerance.
            backoff: Optional ExponentialBackoff for retry logic.
            rate_limiter: Optional RateLimiter for handling 429 responses.
        """
        self._auth_handler = auth_handler
        self._session = session
        self._owns_session = session is None
        self._base_url = base_url.rstrip("/")

        # Store resilience patterns
        self._circuit_breaker = circuit_breaker
        self._backoff = backoff
        self._rate_limiter = rate_limiter

    async def __aenter__(self) -> ThermacellAPI:
        """Enter the context manager.

        Creates session if needed and authenticates with the API.

        Returns:
            Self for use in async with statements.

        Raises:
            Exception: Re-raises any exception after cleaning up resources.
        """
        try:
            # Create session if not provided
            if self._session is None:
                self._session = ClientSession()
                self._owns_session = True

            # Update auth handler's session
            self._auth_handler.set_session(self._session)

            # Enter auth handler context
            await self._auth_handler.__aenter__()
        except Exception:
            # Clean up session on failure
            if self._owns_session and self._session is not None:
                await self._session.close()
                self._session = None
            raise
        else:
            return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the context manager.

        Closes session if it was created by this client.

        Args:
            exc_type: Exception type if an exception occurred.
            exc_val: Exception value if an exception occurred.
            exc_tb: Exception traceback if an exception occurred.
        """
        # Exit auth handler context
        await self._auth_handler.__aexit__(exc_type, exc_val, exc_tb)

        # Close session if we own it
        if self._owns_session and self._session is not None:
            await self._session.close()

    async def request(
        self,
        method: str,
        endpoint: str,
        *,
        json_data: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        retry_auth: bool = True,
        _rate_limit_retries: int = 0,
    ) -> tuple[int, dict[str, Any] | None]:
        """Make an authenticated API request.

        This is the core method for all HTTP communication. It handles:
        - Authentication headers
        - Rate limiting (429 responses)
        - Automatic reauthentication on 401/403
        - Response parsing

        Args:
            method: HTTP method (GET, PUT, POST, DELETE).
            endpoint: API endpoint path (e.g., "/user/nodes").
            json_data: Optional JSON data for request body.
            params: Optional query parameters.
            retry_auth: Whether to retry with reauthentication on 401/403.
            _rate_limit_retries: Internal counter for rate-limit retries (do not set manually).

        Returns:
            Tuple of (status_code, response_data). Response data is None if
            response is not JSON or has no content.

        Raises:
            RuntimeError: If session is not initialized or is closed.
            TimeoutError: If request times out.
            ClientError: If connection fails.
        """
        if self._session is None:
            msg = "Session not initialized. Use 'async with' or provide a session."
            raise RuntimeError(msg)

        if self._session.closed:
            msg = "Session is closed. Cannot make request."
            raise RuntimeError(msg)

        # Ensure we're authenticated
        await self._auth_handler.ensure_authenticated()

        url = f"{self._base_url}/v1{endpoint}"
        headers = {"Authorization": self._auth_handler.access_token or ""}
        timeout = ClientTimeout(total=DEFAULT_TIMEOUT)

        try:
            async with self._session.request(
                method,
                url,
                json=json_data,
                params=params,
                headers=headers,
                timeout=timeout,
            ) as response:
                # Handle rate limiting with bounded retries
                if response.status == HTTPStatus.TOO_MANY_REQUESTS and self._rate_limiter is not None:
                    if _rate_limit_retries >= MAX_RATE_LIMIT_RETRIES:
                        _LOGGER.error(
                            "Rate limit retry exhausted after %d attempts for %s",
                            MAX_RATE_LIMIT_RETRIES,
                            endpoint,
                        )
                        return response.status, None

                    retry_after = response.headers.get("Retry-After")
                    delay = self._rate_limiter.get_retry_delay(response.status, retry_after)
                    _LOGGER.warning(
                        "Rate limited (429), waiting %.2fs before retry (attempt %d/%d)",
                        delay,
                        _rate_limit_retries + 1,
                        MAX_RATE_LIMIT_RETRIES,
                    )
                    await asyncio.sleep(delay)

                    # Retry request after rate limit delay with incremented counter
                    return await self.request(
                        method,
                        endpoint,
                        json_data=json_data,
                        params=params,
                        retry_auth=retry_auth,
                        _rate_limit_retries=_rate_limit_retries + 1,
                    )

                # Handle authentication errors
                if retry_auth and self._auth_handler.should_retry_on_status(response.status):
                    _LOGGER.debug("Received status %d, attempting reauthentication", response.status)
                    await self._auth_handler.handle_auth_retry(response.status)

                    # Retry request with new token
                    return await self.request(
                        method,
                        endpoint,
                        json_data=json_data,
                        params=params,
                        retry_auth=False,  # Don't retry again
                    )

                # Parse response if successful
                response_data = None
                if response.status in (HTTPStatus.OK, HTTPStatus.CREATED, HTTPStatus.NO_CONTENT):
                    # Check content-type with substring match to handle charset parameters
                    # e.g., "application/json; charset=utf-8"
                    if "application/json" in response.content_type:
                        response_data = await response.json()
                    else:
                        response_data = {}

                return response.status, response_data

        except TimeoutError:
            _LOGGER.exception("Request to %s timed out", url)
            raise

        except ClientError:
            _LOGGER.exception("Connection error for %s", url)
            raise

    # -------------------------------------------------------------------------
    # Device Endpoints
    # -------------------------------------------------------------------------

    async def get_nodes(self) -> tuple[int, dict[str, Any] | None]:
        """Get list of all devices (nodes) for the authenticated user.

        Returns:
            Tuple of (status_code, response_data) where response_data has format:
            {"nodes": ["node_id_1", "node_id_2", ...]}
        """
        return await self.request("GET", "/user/nodes")

    async def get_node_params(self, node_id: str) -> tuple[int, dict[str, Any] | None]:
        """Get device parameters (operational state).

        Args:
            node_id: Device's unique identifier.

        Returns:
            Tuple of (status_code, response_data) where response_data has format:
            {"LIV Hub": {"Power": bool, "LED Brightness": int, ...}}
        """
        return await self.request("GET", "/user/nodes/params", params={"nodeid": node_id})

    async def get_node_status(self, node_id: str) -> tuple[int, dict[str, Any] | None]:
        """Get device connectivity status.

        Args:
            node_id: Device's unique identifier.

        Returns:
            Tuple of (status_code, response_data) where response_data has format:
            {"connectivity": {"connected": bool, ...}}
        """
        return await self.request("GET", "/user/nodes/status", params={"nodeid": node_id})

    async def get_node_config(self, node_id: str) -> tuple[int, dict[str, Any] | None]:
        """Get device configuration (model, firmware, serial number).

        Args:
            node_id: Device's unique identifier.

        Returns:
            Tuple of (status_code, response_data) where response_data has format:
            {"info": {"name": str, "type": str, "fw_version": str, ...},
             "devices": [{"serial_num": str, ...}]}
        """
        return await self.request("GET", "/user/nodes/config", params={"nodeid": node_id})

    async def update_node_params(
        self,
        node_id: str,
        params: dict[str, Any],
    ) -> tuple[int, dict[str, Any] | None]:
        """Update device parameters (control device).

        Args:
            node_id: Device's unique identifier.
            params: Parameter updates in format:
                {"LIV Hub": {"Enable Repellers": bool, "LED Brightness": int, ...}}

        Returns:
            Tuple of (status_code, response_data).
        """
        return await self.request(
            "PUT",
            "/user/nodes/params",
            params={"nodeid": node_id},
            json_data=params,
        )

    # -------------------------------------------------------------------------
    # Group Endpoints
    # -------------------------------------------------------------------------

    async def get_groups(self) -> tuple[int, dict[str, Any] | None]:
        """Get list of all groups for the authenticated user.

        Returns:
            Tuple of (status_code, response_data) where response_data has format:
            {"groups": [{"group_id": str, "group_name": str, ...}], "total": int}
        """
        return await self.request("GET", "/user/node_group")

    async def get_group(self, group_id: str) -> tuple[int, dict[str, Any] | None]:
        """Get a specific group by ID.

        Args:
            group_id: Group's unique identifier.

        Returns:
            Tuple of (status_code, response_data) where response_data has format:
            {"groups": [{"group_id": str, "group_name": str, ...}]}
        """
        return await self.request("GET", "/user/node_group", params={"group_id": group_id})

    async def get_group_nodes(self, group_id: str) -> tuple[int, dict[str, Any] | None]:
        """Get node IDs belonging to a group.

        Args:
            group_id: Group's unique identifier.

        Returns:
            Tuple of (status_code, response_data) where response_data has format:
            {"nodes": ["node_id_1", "node_id_2", ...]}
        """
        return await self.request("GET", "/user/nodes", params={"group_id": group_id})

    async def create_group(
        self,
        group_name: str,
        node_ids: list[str] | None = None,
    ) -> tuple[int, dict[str, Any] | None]:
        """Create a new group.

        Args:
            group_name: Name for the new group.
            node_ids: Optional list of node IDs to add to the group.

        Returns:
            Tuple of (status_code, response_data) where response_data has format:
            {"group_id": str}
        """
        payload: dict[str, Any] = {"group_name": group_name}
        if node_ids:
            payload["node_list"] = node_ids

        return await self.request("POST", "/user/node_group", json_data=payload)

    async def update_group(
        self,
        group_id: str,
        group_name: str,
        node_ids: list[str] | None = None,
    ) -> tuple[int, dict[str, Any] | None]:
        """Update an existing group.

        Args:
            group_id: Group's unique identifier.
            group_name: New name for the group.
            node_ids: Optional new list of node IDs (replaces existing nodes).

        Returns:
            Tuple of (status_code, response_data).
        """
        payload: dict[str, Any] = {"group_name": group_name}
        if node_ids is not None:
            payload["node_list"] = node_ids

        return await self.request(
            "PUT",
            "/user/node_group",
            params={"group_id": group_id},
            json_data=payload,
        )

    async def delete_group(self, group_id: str) -> tuple[int, dict[str, Any] | None]:
        """Delete a group.

        Args:
            group_id: Group's unique identifier.

        Returns:
            Tuple of (status_code, response_data).
        """
        return await self.request("DELETE", "/user/node_group", params={"group_id": group_id})
