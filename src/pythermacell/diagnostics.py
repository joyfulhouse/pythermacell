"""Opt-in, direct LAN diagnostic: python -m pythermacell.diagnostics --help."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import logging
import os
import socket
import sys
from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime
from functools import partial
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

from aiohttp import ClientSession, ClientTimeout, DummyCookieJar

from pythermacell.client import ThermacellClient
from pythermacell.const import DEFAULT_BASE_URL, DEVICE_TYPE_LIV_HUB, LED_BRIGHTNESS_MAX
from pythermacell.local import SERVICE_TYPE, LocalTransport
from pythermacell.parsers import parse_device_state
from pythermacell.services import HubServices


if TYPE_CHECKING:
    from collections.abc import Iterator

    from pythermacell._proto.local_pb2 import LocalCtrlMessage
    from pythermacell.local import LocalEndpoint

LED_NAMES = ("LED Brightness", "LED Hue", "LED Saturation", "LED Power")
READ_NAMES = (*LED_NAMES, "Enable Repellers", "System State", "System Status", "Error", "Refill Life")
MAX_BRIGHTNESS = LED_BRIGHTNESS_MAX
MAX_DISCOVERY_SECONDS = 60
CLOUD_URL = f"{DEFAULT_BASE_URL}/"
STAGES = ("discovery", "metadata", "handshake", "identity", "properties", "led_write", "led_readback", "restore")


def stage(report: dict[str, Any], name: str, status: str, **details: Any) -> None:
    """Record only explicitly selected, non-secret evidence."""
    report["stages"][name] = {"status": status, **details}


def selected_values(params: dict[str, Any], names: tuple[str, ...] = READ_NAMES) -> dict[str, Any]:
    """Exclude service values and arbitrary fields, including nested secrets."""
    hub = params.get(DEVICE_TYPE_LIV_HUB, {})
    return {name: hub[name] for name in names if name in hub and type(hub[name]) in (bool, int, float)}


def new_report(node_id: str) -> dict[str, Any]:
    """Create an independently timestamped record for one account node."""
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "node_id": node_id,
        "source": "live",
        "cloud_use": "Account node list, config/local_control metadata and baseline params only; no fallback",
        "stages": {name: {"status": "not_performed"} for name in STAGES},
        "cloud_denial": {"status": "not_performed"},
    }


async def discover(seconds: float) -> list[dict[str, Any]]:
    """Browse with optional zeroconf; persist only address and node-id fields."""
    zc = importlib.import_module("zeroconf.asyncio")
    names: set[str] = set()

    def found(**event: Any) -> None:
        names.add(event["name"])

    network = zc.AsyncZeroconf()
    browser = zc.AsyncServiceBrowser(network.zeroconf, SERVICE_TYPE, handlers=[found])
    try:
        await asyncio.sleep(seconds)
        records = []
        for name in sorted(names):
            info = zc.AsyncServiceInfo(SERVICE_TYPE, name)
            if await info.async_request(network.zeroconf, 2000):
                records.append(
                    {
                        "host": info.server,
                        "addresses": info.parsed_scoped_addresses(),
                        "port": info.port,
                        "node_id": info.properties.get(b"node_id", b"").decode("utf-8", errors="replace"),
                    }
                )
        return records
    finally:
        await browser.async_cancel()
        await network.async_close()


class DiagnosticTransport(LocalTransport):
    """Observe the existing wire implementation without adding cloud fallback."""

    def __init__(self, session: ClientSession, endpoint: LocalEndpoint, report: dict[str, Any]) -> None:
        super().__init__(session, endpoint)
        self.report = report
        self.observing = True

    async def _post(self, path: str, payload: bytes) -> bytes:
        data = await super()._post(path, payload)
        if self.observing and path == "version":
            metadata = json.loads(data)
            version = metadata.get("local_ctrl", metadata.get("prov", {}))
            patch_version = version.get("sec_patch_ver", 0)
            self.report["stages"]["metadata"]["sec2_patch_version"] = (
                patch_version if type(patch_version) is int else None
            )
        return data

    async def _connect(self) -> None:
        try:
            await super()._connect()
        except Exception as exc:
            if self.observing:
                stage(self.report, "handshake", "failed", error_type=type(exc).__name__)
            raise
        else:
            if self.observing:
                stage(self.report, "handshake", "passed")

    async def _control(self, request: LocalCtrlMessage, expected: str, message_type: int) -> LocalCtrlMessage:
        response = await super()._control(request, expected, message_type)
        if self.observing and expected == "resp_get_prop_vals":
            for prop in response.resp_get_prop_vals.props:
                if prop.name == "config" and prop.status == 0:
                    config = json.loads(prop.value)
                    matches = isinstance(config, dict) and config.get("node_id") == self.endpoint.node_id
                    stage(self.report, "identity", "passed" if matches else "failed", matches_account_and_txt=matches)
        return response


def led_settings(config: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """Require a complete scalar snapshot of every advertised LED parameter."""
    advertised = {
        p["name"]
        for device in config.get("devices", [])
        if device.get("name") == DEVICE_TYPE_LIV_HUB
        for p in device.get("params", [])
        if isinstance(p.get("name"), str) and p["name"].startswith("LED ")
    }
    present = {name for name in params.get(DEVICE_TYPE_LIV_HUB, {}) if name.startswith("LED ")}
    values = selected_values(params, LED_NAMES)
    if not advertised or advertised | present != values.keys():
        msg = "Incomplete or unknown LED settings; refusing writes"
        raise ValueError(msg)
    return values


async def restore_led(transport: LocalTransport, original: dict[str, Any], report: dict[str, Any]) -> None:
    """Restore only the changed brightness and verify the entire LED snapshot."""
    try:
        async with asyncio.timeout(45):
            await transport.write({DEVICE_TYPE_LIV_HUB: {"LED Brightness": original["LED Brightness"]}})
            config, params = await transport.read()
            restored = led_settings(config, params)
            stage(report, "restore", "passed" if restored == original else "RESTORE_FAILED", values=restored)
    except Exception as exc:
        stage(report, "restore", "RESTORE_FAILED", error_type=type(exc).__name__)
    if report["stages"]["restore"]["status"] == "RESTORE_FAILED":
        sys.stderr.write(
            "RESTORE_FAILED: STOP all further writes; original LED settings: " + json.dumps(original) + "\n"
        )


async def exercise_led(transport: LocalTransport, report: dict[str, Any]) -> None:
    """Perform one brightness write with verified finally cleanup, even on cancellation."""
    config, params = await transport.read()
    original = led_settings(config, params)
    writable = any(
        p.get("name") == "LED Brightness" and "write" in p.get("properties", [])
        for device in config.get("devices", [])
        if device.get("name") == DEVICE_TYPE_LIV_HUB
        for p in device.get("params", [])
    )
    brightness = original.get("LED Brightness")
    if not writable or type(brightness) is not int or not 0 <= brightness <= MAX_BRIGHTNESS:
        stage(report, "led_write", "unsupported", reason="No valid writable LED Brightness")
        return
    changed = brightness - 1 if brightness else 1
    report["led_before"] = original
    try:
        async with asyncio.timeout(30):
            await transport.write({DEVICE_TYPE_LIV_HUB: {"LED Brightness": changed}})
            stage(report, "led_write", "passed", values={"LED Brightness": changed})
            config, params = await transport.read()
            actual = led_settings(config, params)
            expected = {**original, "LED Brightness": changed}
            stage(report, "led_readback", "passed" if actual == expected else "failed", values=actual)
    except Exception as exc:
        stage(report, "led_write", "failed_or_uncertain", error_type=type(exc).__name__)
    finally:
        # A cancelled/uncertain command may already have reached the hub.
        cleanup = asyncio.create_task(restore_led(transport, original, report))
        try:
            await asyncio.shield(cleanup)
        except asyncio.CancelledError:
            await cleanup
            raise


@contextmanager
def deny_cloud(addresses: set[tuple[str, int]]) -> Iterator[dict[str, Any]]:
    """Restrict TCP connects in this process to discovered LAN endpoints only."""
    connect = socket.socket.connect
    connect_ex = socket.socket.connect_ex
    evidence: dict[str, Any] = {"status": "active", "blocked_connects": 0, "scope": "process TCP sockets"}

    def check(address: Any) -> None:
        if isinstance(address, tuple) and (address[0], address[1]) not in addresses:
            evidence["blocked_connects"] += 1
            msg = "Diagnostic process denies non-LAN connections"
            raise PermissionError(msg)

    def guarded(sock: socket.socket, address: Any) -> None:
        check(address)
        connect(sock, address)

    def guarded_ex(sock: socket.socket, address: Any) -> int:
        check(address)
        return connect_ex(sock, address)

    with patch.object(socket.socket, "connect", guarded), patch.object(socket.socket, "connect_ex", guarded_ex):
        yield evidence


async def probe_denial(evidence: dict[str, Any]) -> None:
    """Attempt an actual cloud request with a fresh session under the guard."""
    try:
        async with (
            ClientSession(timeout=ClientTimeout(total=5), trust_env=False) as session,
            session.get(CLOUD_URL),
        ):
            evidence["status"] = "failed_cloud_reachable"
    except Exception as exc:
        evidence["status"] = "verified" if evidence["blocked_connects"] else "unverified"
        evidence["error_type"] = type(exc).__name__


async def account_nodes() -> list[tuple[str, dict[str, Any], dict[str, Any], HubServices]]:
    """Use cloud only for account membership, metadata, and a comparison snapshot."""
    username, password = os.environ.get("THERMACELL_USERNAME"), os.environ.get("THERMACELL_PASSWORD")
    if not username or not password:
        msg = "Set THERMACELL_USERNAME and THERMACELL_PASSWORD"
        raise ValueError(msg)
    async with asyncio.timeout(60), ThermacellClient(username, password) as client:
        status, data = await client.api.get_nodes()
        if status != HTTPStatus.OK or data is None:
            msg = "Cloud account discovery failed"
            raise RuntimeError(msg)
        result = []
        for node in data.get("nodes", []):
            config_status, config = await client.api.get_node_config(node)
            params_status, params = await client.api.get_node_params(node)
            if config_status != HTTPStatus.OK or params_status != HTTPStatus.OK or config is None or params is None:
                msg = "Cloud metadata fetch failed"
                raise RuntimeError(msg)
            services = HubServices(client.api, partial(parse_device_state, node, params, {}, config))
            result.append((node, config, params, services))
        return result


def metadata_report(services: HubServices) -> dict[str, Any]:
    """Resolve the existing capability parser; expose presence only for credentials."""
    kind = "esp.service.local_control"
    security = services.value(kind, "esp.param.local_control_type")
    return {
        "status": "advertised" if services.parameter(kind, "esp.param.local_control_type") else "not_advertised",
        "security_type": security if type(security) is int else None,
        "sec2_patch_version": None,
        "pop_present": bool(services.value(kind, "esp.param.local_control_pop")),
        "username_present": bool(services.value(kind, "esp.param.local_control_username")),
    }


async def diagnose_node(
    node: str,
    config: dict[str, Any],
    params: dict[str, Any],
    discovered: list[dict[str, Any]],
    *,
    services: HubServices,
    write_led: bool,
    report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run staged direct transport checks for exactly one account node."""
    if report is None:
        report = new_report(node)
    report["name"] = str(params.get(DEVICE_TYPE_LIV_HUB, {}).get("Name", node))
    report["cloud_firmware"] = str(config.get("info", {}).get("fw_version", "unknown"))
    report["cloud_baseline"] = selected_values(params)
    report["stages"]["metadata"] = metadata_report(services)
    matches = [entry for entry in discovered if entry["node_id"] == node]
    stage(report, "discovery", "passed" if matches else "not_found", records=matches)
    if not matches:
        return report
    record = matches[0]
    if not record["addresses"]:
        stage(report, "discovery", "failed", reason="No resolved addresses", records=matches)
        return report
    endpoint = services.local_endpoint(record["addresses"][0], record["port"])
    if endpoint is None:
        report["stages"]["metadata"]["reason"] = "No usable advertised local-control credentials/security"
        return report
    async with ClientSession(cookie_jar=DummyCookieJar(), trust_env=False) as session:
        transport = DiagnosticTransport(session, endpoint, report)
        try:
            async with asyncio.timeout(30):
                local_config, local_params = await transport.read()
        except Exception as exc:
            if report["stages"]["handshake"]["status"] == "passed":
                stage(report, "properties", "failed", error_type=type(exc).__name__)
            return report
        report["local_firmware"] = str(local_config.get("info", {}).get("fw_version", "unknown"))
        stage(report, "properties", "passed", values=selected_values(local_params))
        transport.observing = False
        if write_led:
            try:
                await exercise_led(transport, report)
            except Exception as exc:
                stage(report, "led_write", "failed", error_type=type(exc).__name__)
    return report


def save_report(directory: Path, report: dict[str, Any]) -> None:
    """Write timestamped JSON/text with restrictive permissions, never raw responses."""
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    # Node identifiers are data, never path components.
    stem = f"{stamp}-hub"
    content = json.dumps(report, indent=2, allow_nan=False) + "\n"
    for suffix in ("json", "txt"):
        path = directory / f"{stem}.{suffix}"
        with path.open("x", encoding="utf-8") as stream:
            path.chmod(0o600)
            stream.write(content)
    sys.stdout.write(content)


async def run(args: argparse.Namespace) -> int:
    """Fetch cloud prerequisites first, close cloud sessions, then run LAN only."""
    nodes = await account_nodes()
    discovered = await discover(args.discovery_seconds)
    allowed = {(ip, entry["port"]) for entry in discovered for ip in entry["addresses"]}
    reports = []

    with deny_cloud(allowed) if args.deny_cloud else nullcontext({"status": "not_performed"}) as evidence:
        if args.deny_cloud:
            await probe_denial(evidence)
            if evidence["status"] != "verified":
                args.write_led = False
        for node, config, params, services in nodes:
            if args.node_id and node != args.node_id:
                continue
            report = new_report(node)
            report["cloud_denial"] = dict(evidence)
            try:
                await diagnose_node(
                    node, config, params, discovered, services=services, write_led=args.write_led, report=report
                )
            finally:
                reports.append(report)
                await asyncio.to_thread(save_report, args.output, report)
            if report["stages"]["restore"]["status"] == "RESTORE_FAILED":
                break

    if any(r["stages"]["restore"]["status"] == "RESTORE_FAILED" for r in reports):
        return 3
    if args.deny_cloud and any(r["cloud_denial"]["status"] != "verified" for r in reports):
        return 2
    required: tuple[str, ...] = ("handshake", "identity", "properties")
    if args.write_led:
        required += ("led_write", "led_readback", "restore")
    return 0 if reports and all(r["stages"][s]["status"] == "passed" for r in reports for s in required) else 2


def main() -> int:
    """Parse an explicit write opt-in; suppress third-party logs and secret exceptions."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--discovery-seconds", type=float, default=10)
    parser.add_argument("--node-id")
    parser.add_argument("--write-led", action="store_true", help="Change one brightness value, then restore and verify")
    parser.add_argument("--deny-cloud", action="store_true", help="Deny non-LAN TCP connects during the local phase")
    args = parser.parse_args()
    if not 0 < args.discovery_seconds <= MAX_DISCOVERY_SECONDS:
        parser.error("--discovery-seconds must be greater than zero and at most 60")
    previous_logging = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        report = new_report("unavailable")
        report["prerequisite_failure"] = type(exc).__name__
        save_report(args.output, report)
        return 2
    finally:
        logging.disable(previous_logging)


if __name__ == "__main__":
    sys.exit(main())
