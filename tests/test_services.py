"""HTTP contracts for capability-driven controls and refill sentinels."""

from copy import deepcopy
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web

from pythermacell.api import ThermacellAPI
from pythermacell.devices import ThermacellDevice
from pythermacell.exceptions import DeviceError, InvalidParameterError
from pythermacell.parsers import parse_device_params, parse_device_state
from pythermacell.services import TIMER_ID


@pytest.fixture
async def hub(aiohttp_client: Any) -> Any:
    """Serve real HTTP, accepting only the app's request contracts."""
    config = {
        "devices": [
            {
                "name": "LIV Hub",
                "params": [
                    {"name": "Repellers", "type": "esp.param.power", "properties": ["read", "write"]},
                ],
            }
        ],
        "services": [
            {
                "name": name,
                "type": f"esp.service.{kind}",
                "params": [
                    {"name": param, "type": f"esp.param.{ptype}", "properties": ["read", "write"]},
                ],
            }
            for name, kind, param, ptype in (
                ("Programs", "schedule", "Entries", "schedules"),
                ("Clock", "time", "Zone", "tz"),
                ("Maintenance", "system", "Restart", "reboot"),
            )
        ],
    }
    original = {
        "id": "APP1",
        "name": "Evening",
        "enabled": True,
        "triggers": [{"m": 1080, "d": 127}],
        "action": {"LIV Hub": {"Repellers": True}},
    }
    params = {"Programs": {"Entries": [deepcopy(original)]}}
    state = parse_device_state("hub", deepcopy(params), {}, config)
    calls: list[dict[str, Any]] = []
    flags = {"status": 200}

    async def endpoint(request: web.Request) -> web.Response:
        assert dict(request.query) == {"node_id": "hub"}
        if request.method == "GET":
            return web.json_response(params)
        payload = await request.json()
        calls.append(payload)
        if flags["status"] != 200:
            return web.Response(status=flags["status"])
        for op in payload.get("Programs", {}).get("Entries", []):
            entries = params["Programs"]["Entries"]
            existing = next((item for item in entries if item["id"] == op["id"]), None)
            if op["operation"] in ("add", "edit"):
                if existing:
                    entries.remove(existing)
                entries.append({k: v for k, v in op.items() if k != "operation"})
            elif op["operation"] == "remove":
                entries.remove(existing)
            else:
                existing["enabled"] = op["operation"] == "enable"
        return web.Response(status=204)

    async def firmware(request: web.Request) -> web.Response:
        if request.method == "POST":
            assert await request.json() == {"node_id": "hub", "ota_job_id": "job"}
            return web.Response(status=flags["status"])
        assert request.query["node_id"] == "hub"
        if request.path.endswith("ota_status"):
            assert request.query["ota_job_id"] == "job"
            return web.json_response({"status": "completed", "additional_info": "Installed"})
        return web.json_response(
            {"ota_available": True, "fw_version": "6.0", "ota_job_id": "job", "description": "Fix"}
        )

    app = web.Application()
    app.router.add_route("*", "/v1/user/nodes/params", endpoint)
    app.router.add_route("*", "/v1/user/nodes/ota_update", firmware)
    app.router.add_get("/v1/user/nodes/ota_status", firmware)
    http = await aiohttp_client(app)
    auth = MagicMock(ensure_authenticated=AsyncMock())
    auth.should_retry_on_status.return_value = False
    auth.access_token = "token"
    api = ThermacellAPI(auth_handler=auth, session=http.session, base_url=str(http.make_url("/")))
    device = ThermacellDevice(api, state, enable_queue=False)
    return device, params, calls, flags, original


async def test_native_timer_preserves_app_schedules_and_uses_advertised_names(hub: Any) -> None:
    device, params, calls, _, original = hub
    await device.services.set_shutdown_timer(1800)
    assert calls[0] == {
        "Programs": {
            "Entries": [
                {
                    "id": TIMER_ID,
                    "name": "Timer_HA_shutdown",
                    "operation": "add",
                    "triggers": [{"rsec": 1800}],
                    "action": {"LIV Hub": {"Repellers": False}},
                }
            ]
        }
    }
    assert calls[1] == {"Programs": {"Entries": [{"id": TIMER_ID, "operation": "enable"}]}}
    await device.services.set_shutdown_timer(3600)
    assert calls[2]["Programs"]["Entries"][0]["operation"] == "edit"
    assert params["Programs"]["Entries"][0] == original
    await device.services.cancel_shutdown_timer()
    assert params["Programs"]["Entries"] == [original]
    await device.services.set_schedule_enabled("APP1", False)
    assert params["Programs"]["Entries"][0] == {**original, "enabled": False}
    with pytest.raises(InvalidParameterError):
        await device.services.set_schedule_enabled("deleted", True)


@pytest.mark.parametrize("seconds", [0, -1, 86401, 1.5, True])
async def test_invalid_timer_never_writes(hub: Any, seconds: Any) -> None:
    device, _, calls, _, _ = hub
    with pytest.raises(InvalidParameterError):
        await device.services.set_shutdown_timer(seconds)
    assert not calls


async def test_timer_collision_and_rejection(hub: Any) -> None:
    device, params, calls, flags, _ = hub
    params["Programs"]["Entries"].append({"id": TIMER_ID, "name": "Someone else's"})
    for method in (device.services.cancel_shutdown_timer, lambda: device.services.set_shutdown_timer(30)):
        with pytest.raises(DeviceError, match="belongs"):
            await method()
    assert not calls
    params["Programs"]["Entries"].pop()
    flags["status"] = 400
    with pytest.raises(DeviceError):
        await device.services.set_shutdown_timer(30)
    assert len(calls) == 1  # Never enable a rejected timer.


async def test_timezone_reboot_and_capability_gate(hub: Any) -> None:
    device, _, calls, _, _ = hub
    await device.services.set_timezone("America/New_York")
    await device.services.reboot()
    assert calls == [{"Clock": {"Zone": "America/New_York"}}, {"Maintenance": {"Restart": True}}]
    with pytest.raises(InvalidParameterError):
        await device.services.set_timezone("../invalid")
    device._state.raw_data["config"]["services"] = []
    with pytest.raises(DeviceError):
        await device.services.reboot()
    assert len(calls) == 2


async def test_firmware_job_and_stages(hub: Any) -> None:
    device, _, _, flags, _ = hub
    update = await device.services.check_firmware()
    assert update.available
    assert update.version == "6.0"
    assert update.description == "Fix"
    flags["status"] = 400
    with pytest.raises(DeviceError):
        await device.services.install_firmware(update)
    assert not update.in_progress
    flags["status"] = 202
    await device.services.install_firmware(update)
    assert update.in_progress
    with pytest.raises(InvalidParameterError):
        await device.services.install_firmware(update)
    await device.services.refresh_firmware_status(update)
    assert update.status == "completed"
    assert not update.in_progress


@pytest.mark.parametrize(
    ("value", "life", "present"),
    [
        (-1, None, False),
        (None, None, None),
        (-2, None, None),
        (101, None, None),
        (True, None, None),
        ("0", None, None),
        (float("nan"), None, None),
        (float("inf"), None, None),
        (0, 0.0, True),
        (0.5, 0.5, True),
        (100, 100.0, True),
    ],
)
def test_missing_refill_is_not_empty(value: Any, life: float | None, present: bool | None) -> None:
    params = parse_device_params({"LIV Hub": {"Refill Life": value, "System State": 1}})
    assert params.refill_life == life
    assert params.cartridge_present is present
    assert params.system_status == 1
