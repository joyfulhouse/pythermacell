# Native Services and Local Control

**Category**: API Reference
**Last Updated**: 2026-10-18
**Related**: [APK audit](APK_AUDIT_2026-10-18.md)

Implemented in 0.3.0b1. Contracts come from LIV Android 4.0.5, versionCode
202, and ESP RainMaker CLI commit `dee32b620f5c6307fd572c2836e674b81b60c819`.
Validation uses local HTTP peers; no live hub commands were sent for this release.

## Capabilities

Use `device.services` to resolve advertised service/parameter names. Controls
require the parameter's `write` property; unknown services are never guessed.

| Operation | Service type | Parameter type |
|---|---|---|
| Timers and schedules | `esp.service.schedule` | `esp.param.schedules` |
| Reboot | `esp.service.system` | `esp.param.reboot` |
| Timezone | `esp.service.time` | `esp.param.tz` |

`services.schedules` exposes ID, name, enabled state, triggers, and actions.
`await services.set_schedule_enabled(id, enabled)` sends an operation for that
ID only. It does not replace the schedule array. Mutations first read current
schedule state to detect deletions and ID conflicts.

`await services.set_shutdown_timer(seconds)` adds/edits a native timer with
`triggers: [{"rsec": seconds}]`, an off action using the advertised power
parameter, and a separate `enable` operation. Accepted durations are 1-86400
seconds. The dedicated ID is `HA01`, name `Timer_HA_shutdown`. There is one
integration-owned shutdown timer per hub; conflicting foreign IDs are rejected.
`await services.cancel_shutdown_timer()` removes only that timer.

Install the timer before turning the hub on. Native timers run on the hub after
HA stops. A successful HTTP write is an acknowledgement, not proof the firmware
will execute a future event. Schedule capacity and firmware support still apply.

`await services.set_timezone("America/New_York")` validates an IANA name and
writes only `esp.param.tz`, matching `NodeDetailsAdapter$1`. The app reads
`esp.param.tz_posix` for display but does not send a guessed POSIX string.
`await services.reboot()` writes boolean true to the advertised reboot param.

Evidence: `TimerDetailActivity.prepareScheduleJsonAndUpdate`,
`TimerDetailActivity$2`, `ScheduleAdapter$2`, `SystemServiceAdapter`, and
`NodeDetailsAdapter$1` in the decoded APK.

## Firmware and Groups

See [OTA contracts](OTA_UPDATE_ENDPOINTS.md). Firmware offers are separate cloud
endpoints; their availability is discovered by a successful response.

`api.update_multiple_nodes({node_id: payload})` supports the app's bulk PUT body:
`[{"node_id": "...", "payload": {...}}]` at `/v1/user/nodes/params`, without a
node query parameter. `ApiManager.updateParamsForMultiNode` confirms this shape.
There is no demonstrated group-specific parameter endpoint. HA coordinates
individual verified power commands so it can report per-member failures.

`client.get_groups(strict=True)` and `get_group_nodes(id, strict=True)` raise
on failed reads instead of interpreting failure as an empty membership list.

## Local Transport

`pythermacell.local.SERVICE_TYPE` is `_esp_local_ctrl._tcp.local.`. Match the TXT
`node_id` to a node in the authenticated account. Use
`device.services.local_endpoint(host, port)` to pair that discovery with
`esp.service.local_control` values: `esp.param.local_control_type`,
`esp.param.local_control_pop`, and `esp.param.local_control_username` (default
`wifiprov`, as in the app). Register the result with `client.api.configure_local`.

The transport posts binary protobuf messages to `esp_local_ctrl/session` and
`esp_local_ctrl/control`, with `esp_local_ctrl/version` for Security 2 patch
metadata. It supports the advertised schemes: 0, 1 (X25519/AES-CTR with PoP),
and 2 (SRP6a/SHA512/3072/AES-GCM, patch 0 or 1). It never downgrades a scheme.
Scheme 0 is plaintext by definition and is used only if advertised in the
authenticated hub metadata. Secrets and session keys are not logged/persisted.

Each operation opens a fresh session, reads property count/values, checks the
returned `config.node_id`, and discovers the writable `params` property by name.
It handles session cookies, serializes crypto exchanges, bounds response sizes,
and preserves read-only flags. It does not assume the app's property index 1.

Read failures can fall back to cloud. Writes use the last working transport;
an attempted local write is never automatically replayed via cloud. A timeout
could mean the hub applied the command. The next successful poll selects the
appropriate transport. LAN discovery requires same-network mDNS visibility.
Initial account authentication/discovery still requires cloud access; an existing
session can poll cached local hubs during subsequent cloud outages. Schedules,
power, LED, reset, reboot and timezone use the selected parameter transport;
group discovery and OTA remain cloud operations.

The `.proto` schema and typed SRP adaptation carry Espressif's Apache-2.0
notice; the license is included in `pythermacell/_proto/LICENSE`.

## Refill Values

`refill_life` is a finite percentage in [0, 100], otherwise None.
`cartridge_present` is false for the app's `-1` missing-cartridge sentinel,
true for valid percentages (including zero), and None for unknown readings.
No percentages are clamped or fabricated from invalid data.
