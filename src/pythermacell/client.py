"""Main client for Thermacell API."""

from __future__ import annotations

import asyncio
import logging
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from pythermacell.auth import AuthenticationHandler
from pythermacell.const import DEFAULT_BASE_URL, DEFAULT_TIMEOUT, DEVICE_TYPE_LIV_HUB
from pythermacell.devices import ThermacellDevice
from pythermacell.exceptions import DeviceError, ThermacellConnectionError
from pythermacell.models import DeviceInfo, DeviceParams, DeviceState, DeviceStatus, Group


if TYPE_CHECKING:
    from types import TracebackType

    from pythermacell.resilience import CircuitBreaker, ExponentialBackoff, RateLimiter

_LOGGER = logging.getLogger(__name__)


class ThermacellClient:
    """Main client for interacting with Thermacell devices via ESP RainMaker API.

    This client provides high-level methods for device discovery, state management,
    and control operations. It handles authentication automatically and supports
    session injection for integration with applications like Home Assistant.

    Example:
        Basic usage with automatic session management:

        ```python
        async with ThermacellClient(username="user@example.com", password="password") as client:
            devices = await client.get_devices()
            for device in devices:
                await device.turn_on()
        ```

        Advanced usage with injected session and resilience patterns:

        ```python
        from aiohttp import ClientSession
        from pythermacell import ThermacellClient
        from pythermacell.resilience import CircuitBreaker, ExponentialBackoff

        async with ClientSession() as session:
            breaker = CircuitBreaker(failure_threshold=5)
            backoff = ExponentialBackoff(max_retries=3)

            client = ThermacellClient(
                username="user@example.com",
                password="password",
                session=session,
                circuit_breaker=breaker,
                backoff=backoff,
            )

            async with client:
                devices = await client.get_devices()
        ```

    Attributes:
        base_url: Base URL for the API (default: https://api.iot.thermacell.com).
    """

    def __init__(
        self,
        username: str,
        password: str,
        base_url: str = DEFAULT_BASE_URL,
        *,
        session: ClientSession | None = None,
        auth_handler: AuthenticationHandler | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        backoff: ExponentialBackoff | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        """Initialize the Thermacell client.

        Args:
            username: User's email address for authentication.
            password: User's password for authentication.
            base_url: Base URL for the API. Defaults to Thermacell production API.
            session: Optional aiohttp ClientSession. If not provided, one will be
                created when entering the context manager.
            auth_handler: Optional pre-configured AuthenticationHandler. If not provided,
                one will be created with the given credentials.
            circuit_breaker: Optional CircuitBreaker for fault tolerance.
            backoff: Optional ExponentialBackoff for retry logic.
            rate_limiter: Optional RateLimiter for handling 429 responses.
        """
        self._username = username
        self._password = password
        self._base_url = base_url.rstrip("/")

        self._session = session
        self._owns_session = session is None

        # Create or use provided auth handler
        if auth_handler is not None:
            self._auth_handler = auth_handler
        else:
            self._auth_handler = AuthenticationHandler(
                username=username,
                password=password,
                base_url=base_url,
                session=session,
                circuit_breaker=circuit_breaker,
                backoff=backoff,
                rate_limiter=rate_limiter,
            )

        # Store resilience patterns for use in requests
        self._circuit_breaker = circuit_breaker
        self._backoff = backoff
        self._rate_limiter = rate_limiter

    async def __aenter__(self) -> ThermacellClient:
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

            # Update auth handler's session using public API
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

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        *,
        json_data: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        retry_auth: bool = True,
    ) -> tuple[int, dict[str, Any] | None]:
        """Make an authenticated API request.

        Args:
            method: HTTP method (GET, PUT, POST, etc.).
            endpoint: API endpoint path (e.g., "/user/nodes").
            json_data: Optional JSON data for request body.
            params: Optional query parameters.
            retry_auth: Whether to retry with reauthentication on 401/403.

        Returns:
            Tuple of (status_code, response_data).

        Raises:
            ThermacellConnectionError: If connection fails or timeout occurs.
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
                # Handle rate limiting
                if response.status == HTTPStatus.TOO_MANY_REQUESTS and self._rate_limiter is not None:
                    retry_after = response.headers.get("Retry-After")
                    delay = self._rate_limiter.get_retry_delay(response.status, retry_after)
                    _LOGGER.warning("Rate limited (429), waiting %.2fs before retry", delay)
                    await asyncio.sleep(delay)

                    # Retry request after rate limit delay
                    return await self._make_request(
                        method,
                        endpoint,
                        json_data=json_data,
                        params=params,
                        retry_auth=retry_auth,
                    )

                # Handle authentication errors
                if retry_auth and self._auth_handler.should_retry_on_status(response.status):
                    _LOGGER.debug("Received status %d, attempting reauthentication", response.status)
                    await self._auth_handler.handle_auth_retry(response.status)

                    # Retry request with new token
                    headers["Authorization"] = self._auth_handler.access_token or ""
                    return await self._make_request(
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

        except TimeoutError as exc:
            msg = f"Request to {url} timed out"
            raise ThermacellConnectionError(msg) from exc

        except ClientError as exc:
            msg = f"Connection error for {url}: {exc}"
            raise ThermacellConnectionError(msg) from exc

    async def get_devices(self) -> list[ThermacellDevice]:
        """Get all devices for the authenticated user.

        Fetches device states concurrently for improved performance.

        Returns:
            List of ThermacellDevice instances.

        Raises:
            DeviceError: If device discovery fails.
            ThermacellConnectionError: If connection fails.
        """
        # Get list of node IDs
        status, data = await self._make_request("GET", "/user/nodes")

        if status != HTTPStatus.OK or data is None:
            msg = f"Failed to get devices: HTTP {status}"
            raise DeviceError(msg)

        node_ids = data.get("nodes", [])
        if not node_ids:
            return []

        # Fetch full state for all devices concurrently
        states = await asyncio.gather(
            *[self.get_device_state(node_id) for node_id in node_ids],
            return_exceptions=False,
        )

        # Create device objects from states (filter out None states)
        devices: list[ThermacellDevice] = []
        for state in states:
            if state is not None:
                device = ThermacellDevice(client=self, state=state)
                devices.append(device)

        return devices

    async def get_device(self, node_id: str) -> ThermacellDevice | None:
        """Get a specific device by node ID.

        Args:
            node_id: The device's node ID.

        Returns:
            ThermacellDevice instance if found, None otherwise.

        Raises:
            ThermacellConnectionError: If connection fails.
        """
        state = await self.get_device_state(node_id)
        if state is None:
            return None

        return ThermacellDevice(client=self, state=state)

    async def get_device_state(self, node_id: str) -> DeviceState | None:
        """Get complete device state including info, status, and parameters.

        This method fetches three separate API endpoints to build complete device state:
        1. /user/nodes/params - Device parameters (power, LED, refill, runtime, etc.)
        2. /user/nodes/status - Connectivity status (online/offline)
        3. /user/nodes/config - Device info (model, firmware, serial number)

        Args:
            node_id: The device's node ID.

        Returns:
            DeviceState instance if successful, None if device not found.

        Raises:
            ThermacellConnectionError: If connection fails.
        """
        # Fetch parameters (contains device operational state)
        params_status, params_data = await self._make_request("GET", "/user/nodes/params", params={"nodeid": node_id})

        if params_status == HTTPStatus.NOT_FOUND:
            _LOGGER.debug("Device %s not found", node_id)
            return None

        if params_status != HTTPStatus.OK or params_data is None:
            _LOGGER.warning("Failed to fetch params for device %s: HTTP %d", node_id, params_status)
            return None

        # Fetch status
        status_status, status_data = await self._make_request("GET", "/user/nodes/status", params={"nodeid": node_id})

        if status_status != HTTPStatus.OK or status_data is None:
            _LOGGER.warning("Failed to fetch status for device %s: HTTP %d", node_id, status_status)
            return None

        # Fetch config
        config_status, config_data = await self._make_request("GET", "/user/nodes/config", params={"nodeid": node_id})

        if config_status != HTTPStatus.OK or config_data is None:
            _LOGGER.warning("Failed to fetch config for device %s: HTTP %d", node_id, config_status)
            return None

        # Parse responses into models
        device_params = self._parse_device_params(params_data)
        device_status = self._parse_device_status(node_id, status_data)
        device_info = self._parse_device_info(node_id, config_data)

        return DeviceState(
            info=device_info,
            status=device_status,
            params=device_params,
            raw_data={
                "params": params_data,
                "status": status_data,
                "config": config_data,
            },
        )

    async def update_device_params(self, node_id: str, params: dict[str, Any]) -> bool:
        """Update device parameters.

        Args:
            node_id: The device's node ID.
            params: Parameter updates in API format (e.g., {"LIV Hub": {"Power": True}}).

        Returns:
            True if successful, False otherwise.

        Raises:
            ValueError: If params structure is invalid.
            ThermacellConnectionError: If connection fails.
        """
        # Validate params structure
        if not params or not isinstance(params, dict):
            msg = "Params must be a non-empty dictionary"
            raise ValueError(msg)

        # Log the update for debugging
        _LOGGER.debug("Updating device %s params: %s", node_id, params)

        status, _ = await self._make_request("PUT", "/user/nodes/params", params={"nodeid": node_id}, json_data=params)

        success = status in (HTTPStatus.OK, HTTPStatus.NO_CONTENT)
        if success:
            _LOGGER.debug("Successfully updated device %s", node_id)
        else:
            _LOGGER.warning("Failed to update device %s: HTTP %d", node_id, status)

        return success

    async def get_groups(self) -> list[Group]:
        """Get all groups for the authenticated user.

        Returns:
            List of Group instances. Returns empty list if no groups exist.

        Raises:
            ThermacellConnectionError: If connection fails.
            AuthenticationError: If authentication fails.
        """
        status, data = await self._make_request("GET", "/user/node_group")

        if status != HTTPStatus.OK or data is None:
            _LOGGER.warning("Failed to get groups: HTTP %d", status)
            return []

        groups_data = data.get("groups", [])
        groups: list[Group] = []

        for group_data in groups_data:
            group = Group(
                group_id=group_data["group_id"],
                group_name=group_data["group_name"],
                is_matter=group_data.get("is_matter", False),
                primary=group_data.get("primary", False),
                total=group_data.get("total", 0),
            )
            groups.append(group)

        _LOGGER.debug("Found %d group(s)", len(groups))
        return groups

    async def get_group(self, group_id: str) -> Group | None:
        """Get a specific group by ID.

        Args:
            group_id: The group's unique identifier.

        Returns:
            Group instance if found, None otherwise.

        Raises:
            ThermacellConnectionError: If connection fails.
            AuthenticationError: If authentication fails.
        """
        status, data = await self._make_request("GET", "/user/node_group", params={"group_id": group_id})

        if status != HTTPStatus.OK or data is None:
            _LOGGER.warning("Failed to get group %s: HTTP %d", group_id, status)
            return None

        groups_data = data.get("groups", [])
        if not groups_data:
            _LOGGER.debug("Group %s not found", group_id)
            return None

        # API returns single-element array
        group_data = groups_data[0]
        return Group(
            group_id=group_data["group_id"],
            group_name=group_data["group_name"],
            is_matter=group_data.get("is_matter", False),
            primary=group_data.get("primary", False),
            total=group_data.get("total", 0),
        )

    async def get_group_nodes(self, group_id: str) -> list[str]:
        """Get node IDs belonging to a group.

        Args:
            group_id: The group's unique identifier.

        Returns:
            List of node IDs in the group. Returns empty list if group is empty or doesn't exist.

        Raises:
            ThermacellConnectionError: If connection fails.
            AuthenticationError: If authentication fails.
        """
        status, data = await self._make_request("GET", "/user/nodes", params={"group_id": group_id})

        if status != HTTPStatus.OK or data is None:
            _LOGGER.warning("Failed to get nodes for group %s: HTTP %d", group_id, status)
            return []

        nodes: list[str] = data.get("nodes", [])
        _LOGGER.debug("Group %s has %d node(s)", group_id, len(nodes))
        return nodes

    async def get_group_devices(self, group_id: str) -> list[ThermacellDevice]:
        """Get full device objects for all devices in a group.

        This is a convenience method that combines get_group_nodes() with get_devices()
        to return ThermacellDevice instances instead of just node IDs.

        Args:
            group_id: The group's unique identifier.

        Returns:
            List of ThermacellDevice instances in the group.

        Raises:
            ThermacellConnectionError: If connection fails.
            AuthenticationError: If authentication fails.
        """
        # Get node IDs in the group
        node_ids = await self.get_group_nodes(group_id)

        if not node_ids:
            return []

        # Get all devices
        all_devices = await self.get_devices()

        # Filter devices by group membership
        group_devices = [device for device in all_devices if device.node_id in node_ids]

        _LOGGER.debug("Group %s has %d device(s)", group_id, len(group_devices))
        return group_devices

    async def create_group(self, group_name: str, node_ids: list[str] | None = None) -> str:
        """Create a new group.

        Args:
            group_name: Name for the new group.
            node_ids: Optional list of node IDs to add to the group.

        Returns:
            The newly created group ID.

        Raises:
            ValueError: If group_name is empty.
            ThermacellConnectionError: If connection fails.
            AuthenticationError: If authentication fails.
        """
        if not group_name or not group_name.strip():
            msg = "Group name cannot be empty"
            raise ValueError(msg)

        payload: dict[str, Any] = {"group_name": group_name.strip()}
        if node_ids:
            payload["node_list"] = node_ids

        _LOGGER.debug("Creating group '%s' with %d nodes", group_name, len(node_ids) if node_ids else 0)

        status, data = await self._make_request("POST", "/user/node_group", json_data=payload)

        if status != HTTPStatus.OK or data is None:
            msg = f"Failed to create group: HTTP {status}"
            _LOGGER.error(msg)
            raise DeviceError(msg)

        group_id: str | None = data.get("group_id")
        if not group_id:
            msg = "No group_id returned from create group API"
            raise DeviceError(msg)

        _LOGGER.info("Successfully created group '%s' with ID %s", group_name, group_id)
        return group_id

    async def update_group(
        self,
        group_id: str,
        group_name: str | None = None,
        node_ids: list[str] | None = None,
    ) -> bool:
        """Update an existing group.

        Args:
            group_id: The group's unique identifier.
            group_name: Optional new name for the group.
            node_ids: Optional new list of node IDs (replaces existing nodes).

        Returns:
            True if successful, False otherwise.

        Raises:
            ValueError: If neither group_name nor node_ids is provided.
            ThermacellConnectionError: If connection fails.
            AuthenticationError: If authentication fails.
        """
        if not group_name and node_ids is None:
            msg = "Must provide either group_name or node_ids to update"
            raise ValueError(msg)

        # Get current group info to preserve unmodified fields
        current_group = await self.get_group(group_id)
        if not current_group:
            _LOGGER.warning("Group %s not found", group_id)
            return False

        payload: dict[str, Any] = {}
        # Always include group_name (use current name if not updating)
        payload["group_name"] = group_name.strip() if group_name else current_group.group_name
        if node_ids is not None:
            payload["node_list"] = node_ids

        _LOGGER.debug("Updating group %s", group_id)

        status, _ = await self._make_request(
            "PUT",
            "/user/node_group",
            params={"group_id": group_id},
            json_data=payload,
        )

        success = status == HTTPStatus.OK
        if success:
            _LOGGER.info("Successfully updated group %s", group_id)
        else:
            _LOGGER.warning("Failed to update group %s: HTTP %d", group_id, status)

        return success

    async def delete_group(self, group_id: str) -> bool:
        """Delete a group.

        Args:
            group_id: The group's unique identifier.

        Returns:
            True if successful, False otherwise.

        Raises:
            ThermacellConnectionError: If connection fails.
            AuthenticationError: If authentication fails.
        """
        _LOGGER.debug("Deleting group %s", group_id)

        status, _ = await self._make_request(
            "DELETE",
            "/user/node_group",
            params={"group_id": group_id},
        )

        success = status == HTTPStatus.OK
        if success:
            _LOGGER.info("Successfully deleted group %s", group_id)
        else:
            _LOGGER.warning("Failed to delete group %s: HTTP %d", group_id, status)

        return success

    def _parse_device_params(self, data: dict[str, Any]) -> DeviceParams:
        """Parse device parameters from API response.

        The Thermacell API has two power-related fields:
        - "Power": Read-only status indicator (not used for control)
        - "Enable Repellers": Writable control parameter (actual device power)

        LED state logic: The LED is only considered "on" when BOTH conditions are met:
        1. Device is powered on (enable_repellers=True)
        2. LED brightness is greater than 0

        This matches the physical device behavior where the LED cannot be on
        when the device itself is off, even if brightness is set to a non-zero value.

        Args:
            data: Raw parameter data from API in format:
                  {"LIV Hub": {"Power": bool, "LED Brightness": int, ...}}

        Returns:
            DeviceParams instance with parsed and calculated state.
        """
        hub_params = data.get(DEVICE_TYPE_LIV_HUB, {})

        # Use "Enable Repellers" for device power (not "Power" which is read-only)
        enable_repellers = hub_params.get("Enable Repellers")
        brightness = hub_params.get("LED Brightness", 0)

        # Calculate LED power state: only "on" when hub powered AND brightness > 0
        # This matches physical device behavior and prevents confusion
        led_power = enable_repellers and brightness > 0 if enable_repellers is not None else None

        return DeviceParams(
            power=enable_repellers,  # Use enable_repellers for power status
            led_power=led_power,  # Calculated from enable_repellers and brightness
            led_brightness=brightness,
            led_hue=hub_params.get("LED Hue"),
            led_saturation=hub_params.get("LED Saturation"),
            refill_life=hub_params.get("Refill Life"),
            system_runtime=hub_params.get("System Runtime"),
            system_status=hub_params.get("System Status"),
            error=hub_params.get("Error"),
            enable_repellers=enable_repellers,
        )

    def _parse_device_status(self, node_id: str, data: dict[str, Any]) -> DeviceStatus:
        """Parse device status from API response.

        Args:
            node_id: Device node ID.
            data: Raw status data from API.

        Returns:
            DeviceStatus instance.
        """
        connectivity = data.get("connectivity", {})
        connected = connectivity.get("connected", False)

        return DeviceStatus(node_id=node_id, connected=connected)

    def _parse_device_info(self, node_id: str, data: dict[str, Any]) -> DeviceInfo:
        """Parse device info from API response.

        Args:
            node_id: Device node ID.
            data: Raw config data from API.

        Returns:
            DeviceInfo instance.
        """
        info = data.get("info", {})
        devices = data.get("devices", [{}])
        device_data = devices[0] if devices else {}

        # Convert model name to user-friendly format
        model_type = info.get("type", "")
        model = "Thermacell LIV Hub" if model_type == "thermacell-hub" else model_type

        return DeviceInfo(
            node_id=node_id,
            name=info.get("name", node_id),
            model=model,
            firmware_version=info.get("fw_version", "unknown"),
            serial_number=device_data.get("serial_num", "unknown"),
        )
