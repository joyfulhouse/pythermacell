"""Capability-driven RainMaker services verified against the LIV Android app."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pythermacell.exceptions import DeviceError, InvalidParameterError
from pythermacell.local import LocalEndpoint
from pythermacell.parsers import get_power_parameter_name


if TYPE_CHECKING:
    from collections.abc import Callable

    from pythermacell.api import ThermacellAPI
    from pythermacell.models import DeviceState

TIMER_ID = "HA01"
TIMER_NAME = "Timer_HA_shutdown"
MAX_TIMER_SECONDS = 86400


@dataclass(frozen=True)
class ServiceParameter:
    """An advertised parameter; names are firmware-defined, types are stable."""

    service: str
    name: str
    writable: bool


@dataclass(frozen=True)
class Schedule:
    """A hub schedule, including native countdown timers."""

    id: str
    name: str
    enabled: bool | None
    triggers: list[dict[str, Any]] = field(default_factory=list)
    action: dict[str, Any] = field(default_factory=dict)


@dataclass
class FirmwareUpdate:
    """Cloud OTA metadata. The API reports stages, not a percent complete."""

    available: bool = False
    version: str | None = None
    job_id: str | None = None
    description: str | None = None
    status: str | None = None
    additional_info: str | None = None

    @property
    def in_progress(self) -> bool:
        """Return whether the server reports an active update."""
        return self.status in ("triggered", "started", "in-progress")


class HubServices:
    """Operate only services advertised by a hub's node configuration."""

    def __init__(self, api: ThermacellAPI, state: Callable[[], DeviceState]) -> None:
        """Keep a reference to current state, including after device refresh."""
        self._api = api
        self._state = state
        self._schedule_lock = asyncio.Lock()

    def parameter(self, service_type: str, param_type: str) -> ServiceParameter | None:
        """Resolve a service and parameter by semantic type."""
        for service in self._state().raw_data.get("config", {}).get("services", []):
            if service.get("type") != service_type or not isinstance(service.get("name"), str):
                continue
            for param in service.get("params", []):
                if param.get("type") == param_type and isinstance(param.get("name"), str):
                    return ServiceParameter(service["name"], param["name"], "write" in param.get("properties", []))
        return None

    def value(self, service_type: str, param_type: str) -> Any:
        """Read a service value without exposing unrelated parameters/secrets."""
        param = self.parameter(service_type, param_type)
        if param is None:
            return None
        return self._state().raw_data.get("params", {}).get(param.service, {}).get(param.name)

    def supports(self, service_type: str, param_type: str) -> bool:
        """Return whether the parameter exists and is writable."""
        param = self.parameter(service_type, param_type)
        return param is not None and param.writable

    def local_endpoint(self, host: str, port: int) -> LocalEndpoint | None:
        """Pair discovery with security settings supplied by this hub's config."""
        kind = "esp.service.local_control"
        security = self.value(kind, "esp.param.local_control_type")
        pop = self.value(kind, "esp.param.local_control_pop")
        username = self.value(kind, "esp.param.local_control_username")
        if type(security) is not int or security not in (0, 1, 2):
            return None
        if security != 0 and not isinstance(pop, str):
            return None
        return LocalEndpoint(self._state().info.node_id, host, port, security, pop or "", username or "wifiprov")

    async def _write(self, service_type: str, param_type: str, value: Any) -> None:
        param = self.parameter(service_type, param_type)
        if param is None or not param.writable:
            msg = f"Hub does not advertise writable {param_type}"
            raise DeviceError(msg)
        status, data = await self._api.update_node_params(
            self._state().info.node_id, {param.service: {param.name: value}}
        )
        if status not in (200, 204) or (data and data.get("status") in ("failure", "failed", "error")):
            msg = f"Service command failed: HTTP {status}"
            raise DeviceError(msg)

    @property
    def schedules(self) -> list[Schedule]:
        """Return schedules from the last reported parameter snapshot."""
        values = self.value("esp.service.schedule", "esp.param.schedules")
        if not isinstance(values, list):
            return []
        return [
            Schedule(
                id=item["id"],
                name=str(item.get("name", item["id"])),
                enabled=item.get("enabled") if isinstance(item.get("enabled"), bool) else None,
                triggers=deepcopy(item.get("triggers", [])),
                action=deepcopy(item.get("action", {})),
            )
            for item in values
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ]

    async def set_schedule_enabled(self, schedule_id: str, enabled: bool) -> None:
        """Enable/disable one schedule without replacing any actions/triggers."""
        async with self._schedule_lock:
            await self._refresh_schedules()
            if not any(s.id == schedule_id for s in self.schedules):
                msg = "Schedule no longer exists; refresh before changing it"
                raise InvalidParameterError(msg)
            await self._schedule_operation({"id": schedule_id, "operation": "enable" if enabled else "disable"})

    async def _refresh_schedules(self) -> None:
        param = self.parameter("esp.service.schedule", "esp.param.schedules")
        if param is None or not param.writable:
            msg = "Hub does not advertise writable schedules"
            raise DeviceError(msg)
        status, data = await self._api.get_node_params(self._state().info.node_id)
        if status != HTTPStatus.OK or not isinstance(data, dict) or param.service not in data:
            msg = "Cannot read the current schedule state"
            raise DeviceError(msg)
        self._state().raw_data.setdefault("params", {})[param.service] = data[param.service]

    async def _schedule_operation(self, operation: dict[str, Any]) -> None:
        await self._write("esp.service.schedule", "esp.param.schedules", [operation])

    async def set_shutdown_timer(self, seconds: int) -> None:
        """Install and enable the integration's native shutdown timer.

        Program the timer before starting the hub. A timeout is ambiguous: callers
        must not retry by starting the hub without a confirmed timer.
        """
        if type(seconds) is not int or not 1 <= seconds <= MAX_TIMER_SECONDS:
            msg = "Timer must be between 1 second and 24 hours"
            raise InvalidParameterError(msg)
        async with self._schedule_lock:
            await self._refresh_schedules()
            existing = next((s for s in self.schedules if s.id == TIMER_ID), None)
            if existing and existing.name != TIMER_NAME:
                msg = "Timer ID belongs to another schedule"
                raise DeviceError(msg)
            power_name = get_power_parameter_name(self._state().raw_data.get("config", {}))
            await self._schedule_operation(
                {
                    "id": TIMER_ID,
                    "name": TIMER_NAME,
                    "operation": "edit" if existing else "add",
                    "triggers": [{"rsec": seconds}],
                    "action": {"LIV Hub": {power_name: False}},
                }
            )
            # The app explicitly enables a timer after add/edit.
            await self._schedule_operation({"id": TIMER_ID, "operation": "enable"})

    async def cancel_shutdown_timer(self) -> None:
        """Remove only this integration's timer, leaving app schedules intact."""
        async with self._schedule_lock:
            await self._refresh_schedules()
            existing = next((s for s in self.schedules if s.id == TIMER_ID), None)
            if existing and existing.name != TIMER_NAME:
                msg = "Timer ID belongs to another schedule"
                raise DeviceError(msg)
            if existing:
                await self._schedule_operation({"id": TIMER_ID, "operation": "remove"})

    @property
    def timezone(self) -> str | None:
        """Return the IANA timezone reported by the hub."""
        value = self.value("esp.service.time", "esp.param.tz")
        return value if isinstance(value, str) else None

    async def set_timezone(self, timezone: str) -> None:
        """Set an IANA timezone using the same parameter as the app."""
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError) as err:
            msg = "Unknown IANA timezone"
            raise InvalidParameterError(msg) from err
        await self._write("esp.service.time", "esp.param.tz", timezone)

    async def reboot(self) -> None:
        """Reboot a hub that explicitly advertises the reboot parameter."""
        await self._write("esp.service.system", "esp.param.reboot", True)

    async def check_firmware(self) -> FirmwareUpdate:
        """Fetch the update offered for this specific node."""
        status, data = await self._api.get_firmware_update(self._state().info.node_id)
        if status != HTTPStatus.OK or not isinstance(data, dict) or "ota_available" not in data:
            msg = f"Firmware check failed: HTTP {status}"
            raise DeviceError(msg)
        return FirmwareUpdate(
            available=data.get("ota_available") is True,
            version=data.get("fw_version") or None,
            job_id=data.get("ota_job_id") or None,
            description=data.get("description") or None,
            status=data.get("status") or None,
        )

    async def install_firmware(self, update: FirmwareUpdate) -> None:
        """Install only an offered OTA job; never accept an arbitrary image URL."""
        if not update.available or not update.job_id or update.in_progress:
            msg = "No installable firmware update"
            raise InvalidParameterError(msg)
        status, data = await self._api.start_firmware_update(self._state().info.node_id, update.job_id)
        if status not in (200, 202, 204) or (data and data.get("status") in ("failure", "failed", "error")):
            msg = f"Firmware installation request failed: HTTP {status}"
            raise DeviceError(msg)
        update.status = "triggered"

    async def refresh_firmware_status(self, update: FirmwareUpdate) -> None:
        """Refresh the server's stage for a known OTA job."""
        if not update.job_id:
            return
        status, data = await self._api.get_firmware_status(self._state().info.node_id, update.job_id)
        if status != HTTPStatus.OK or not isinstance(data, dict) or not isinstance(data.get("status"), str):
            msg = f"Firmware status failed: HTTP {status}"
            raise DeviceError(msg)
        update.status = data["status"]
        update.additional_info = data.get("additional_info")
