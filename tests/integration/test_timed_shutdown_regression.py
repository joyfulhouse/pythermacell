"""Explicitly opted-in reproduction of the firmware 5.4.7 shutdown report."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING

import pytest


if TYPE_CHECKING:
    from pythermacell import ThermacellClient

_LOGGER = logging.getLogger(__name__)
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("THERMACELL_TIMED_SHUTDOWN_REGRESSION") != "1",
        reason="Hardware regression requires explicit opt-in",
    ),
]


def shutdown_report(params: dict) -> dict:
    """Allowlist shutdown evidence; never log configuration or repeller identifiers."""
    hub = params.get("LIV Hub", {})
    return {key: hub.get(key) for key in ("Enable Repellers", "System State", "System Status", "Error")}


def confirmed_off(params: dict) -> bool:
    report = shutdown_report(params)
    return (
        report["Enable Repellers"] is False
        and type(report["System State"]) is int
        and type(report["System Status"]) is int
        and report["System State"] == report["System Status"] == 1
    )


async def test_native_timer_then_run_for_shutdown(
    shared_integration_client: ThermacellClient, test_node_id: str | None
) -> None:
    """Capture raw reports without changing LED settings or refill counters."""
    if os.getenv("THERMACELL_TIMED_SHUTDOWN_REGRESSION") != "1" or not test_node_id:
        pytest.skip("Requires explicit THERMACELL_TIMED_SHUTDOWN_REGRESSION=1 and THERMACELL_TEST_NODE_ID")
    device = await shared_integration_client.get_device(test_node_id)
    assert device is not None
    assert device.is_online
    assert not device.services.schedules, "Use an off test hub with no existing schedules"
    status, baseline = await shared_integration_client.api.get_node_params(test_node_id)
    assert status == 200
    assert isinstance(baseline, dict)
    hub = baseline["LIV Hub"]
    assert hub.get("Enable Repellers") is False
    assert hub.get("System State") == hub.get("System Status") == 1
    cleanup_confirmed = False
    try:
        await device.services.set_shutdown_timer(20)
        assert await device.set_power(True, verify=True)
        await asyncio.sleep(25)
        status, expired = await shared_integration_client.api.get_node_params(test_node_id)
        _LOGGER.info("Native 20-second timer result: %s %s", status, shutdown_report(expired or {}))
        assert status == 200
        assert isinstance(expired, dict)
        expired_on_time = confirmed_off(expired)
        if not expired_on_time:
            # Collect settling evidence even when the first native-expiry assertion fails.
            for poll in range(6):
                await asyncio.sleep(5)
                status, reported = await shared_integration_client.api.get_node_params(test_node_id)
                _LOGGER.warning("Native expiry poll %s: %s %s", poll + 1, status, shutdown_report(reported or {}))
                if status == 200 and isinstance(reported, dict) and confirmed_off(reported):
                    break
        assert expired_on_time, f"Native expiry did not confirm operational Off: {shutdown_report(expired)}"

        await device.services.set_shutdown_timer(60)
        assert await device.set_power(True, verify=True)
        cleanup_confirmed = await device.set_power(False, verify=True)
        # Keep collecting after failure to distinguish slow settling from a stuck report.
        if not cleanup_confirmed:
            for poll in range(12):
                await asyncio.sleep(5)
                status, reported = await shared_integration_client.api.get_node_params(test_node_id)
                _LOGGER.warning("Off recovery poll %s: %s %s", poll + 1, status, shutdown_report(reported or {}))
        assert cleanup_confirmed, "Off command was accepted but operational shutdown was not confirmed"
    finally:
        # Always attempt verified off; retain the native safeguard if confirmation fails.
        cleanup_confirmed = await device.set_power(False, verify=True)
        if cleanup_confirmed:
            await device.services.cancel_shutdown_timer()
        else:
            _LOGGER.error("Cleanup could not confirm shutdown; native timer retained; inspect the hub")
        assert cleanup_confirmed, "Cleanup could not confirm shutdown"
