# Native Services and Local Control

**Category**: API Reference
**Last Updated**: 2026-10-18
**Related**: [APK audit](APK_AUDIT_2026-10-18.md)

Implemented in 0.3.0b1. Contracts come from LIV Android 4.0.5, versionCode
202, and ESP RainMaker CLI commit `dee32b620f5c6307fd572c2836e674b81b60c819`.
Validation uses local HTTP peers; no live hub commands were sent for this release.
For the subsequent opt-in live spike and its limitations, see
[LAN diagnostics](#lan-diagnostic-spike).

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

## LAN Diagnostic Spike

Run from a host on the hubs' LAN with multicast DNS visibility. A pod network
address or working cloud DNS does not establish that visibility. The hub must
advertise `_esp_local_ctrl._tcp.local.` with a TXT `node_id` belonging to the
account, and its cloud config/params must supply `esp.service.local_control`
security metadata. The tool does not invent endpoints, PoP, or security modes.

The optional discovery dependency is `zeroconf` (validated with latest stable
0.151.5 on 2026-10-18). It is needed only for this diagnostic, not normal library
use. From the repository, with `THERMACELL_USERNAME` and `THERMACELL_PASSWORD`
in an existing private environment file:

```bash
# Read-only first; no device parameter writes.
uv run --with zeroconf --env-file /private/thermacell.env \
  python -m pythermacell.diagnostics --output /private/lan-results

# Only after a supported hub passes the read-only stages:
uv run --with zeroconf --env-file /private/thermacell.env \
  python -m pythermacell.diagnostics --output /private/lan-results \
  --node-id ACCOUNT_NODE_ID --write-led

# Actual process-scoped denial after fetching cloud prerequisites:
uv run --with zeroconf --env-file /private/thermacell.env \
  python -m pythermacell.diagnostics --output /private/lan-results --deny-cloud
```

Environment variables may instead be supplied by a secret manager; omit
`--env-file` in that case. Do not put credentials in command arguments. Discovery
waits 10 seconds by default; `--discovery-seconds` accepts up to 60 seconds.
`--node-id` selects one account node; omission checks each node sequentially.

Cloud use is explicitly limited to account membership, local-control metadata,
firmware, and a baseline parameter snapshot. Cloud sessions close before the
LAN phase. The diagnostic uses a `LocalTransport` subclass that observes the
existing protocol; it never registers a cloud-fallback transport. Each artifact
reports discovery (host, all addresses, port, TXT node ID), metadata (security,
Security 2 patch version when available, credential **presence only**), handshake,
identity, properties, LED write, readback, and restoration independently.
`not_performed` means that stage was not reached, not success. Cloud and local
firmware/values are labeled separately; snapshots can differ with timing.

`--write-led` captures all advertised/current LED settings and refuses unknown
or missing LED parameters. It changes only `LED Brightness` by one unit, checks
local readback, and restores the original brightness in `finally`, including
after an uncertain write or cancellation. It then verifies **all** original LED
values. After a definite device rejection of the change write,
`verified_unchanged` means a local read matches the snapshot and no restore write
was needed. After an uncertain write, cleanup writes the original brightness
even if its initial read appears unchanged, then verifies by readback. Repeated
asyncio task cancellation is shielded, but a second real Ctrl-C during an active
restore can abandon cleanup: that failure prints `RESTORE_FAILED` with the
original values and exits 3. Allow cleanup to finish after the first Ctrl-C.
Saturation is captured and checked but never sent, per
[LED control](LED_CONTROL.md). No power, refill, schedule, timer, reboot or OTA
commands are issued. SIGKILL, machine loss, or loss of hub connectivity cannot
guarantee restoration. `RESTORE_FAILED` is
printed with the original LED values and stops further hub writes. Do not rerun
write mode until restoration has been resolved.

JSON and human-readable text artifacts are timestamped per node in a mode-0700
directory, with mode-0600 files. Reports project only selected fields; raw cloud
responses, authentication data, cookies, and exception messages are excluded.
Names and firmware accept only bounded strings or integers; structured metadata
is marked `<invalid type>`. Known credentials are redacted from those strings.
Before writing either artifact or stdout, a narrow self-check refuses output
containing a loaded account username/password, access token, PoP, or local
username. The transient ID token is not stored by the library or exposed to this
diagnostic; it is never projected into report fields. The check also covers
JSON-escaped values. It does not detect unknown or
transformed secrets, inspect other logs, or revoke credentials. Output access is
checked before hub operations. A safe prerequisite reason distinguishes missing
credentials, optional zeroconf, unknown account nodes, and authentication/network
failures; external exception messages remain withheld. A refused hub report is
replaced by a minimal stage-status stub with the refusal reason, omitting its
identity, timestamp, and values. Other hubs can still be checked. If even the
constant stub text matches a credential, it too is withheld without bypassing
the self-check. Any refusal makes the run unsuccessful; a restoration failure
still stops later writes and takes exit-code precedence.
Normal and third-party logs are disabled by the standalone command. Exit status
is 0 for all requested stages passing, 2 for missing prerequisites/unsupported
or failed stages, 3 whenever a restoration failure was recorded (including
during interruption or reporting failure), and 130 for interruption without a
recorded restoration failure. The cleanup attempt has a 45-second bound; initial
local reads and LED write/readback have separate 30-second bounds.

`--deny-cloud` restricts TCP connects **inside this process** to discovered hub
addresses/ports, and attempts a fresh cloud HTTPS request to verify the guard.
It never changes DNS, router, or firewall settings. DNS resolution itself is
allowed. An unverified guard disables LED writes. Reports distinguish a verified
blocked connection from merely selecting `LocalTransport`. A missing LAN
endpoint still prevents proving local reads/writes during a cloud outage.
IPv6 scope names and numeric socket scope IDs refer to the same interface; other
scopes remain denied. Reads try discovered addresses in order of IPv4, global
(or unique-local) IPv6, then link-local IPv6. Each candidate has a 30-second read
bound. LED writes and their restoration stay on the successfully read endpoint;
an uncertain write is never retried at another address.

### If a Secret Leaks

Stop sharing the affected artifacts and restrict or remove exposed copies,
including CI logs and downloads. Change the cloud account password and invalidate
affected sessions/tokens using supported account or vendor controls. Existing
tokens may remain valid for their remaining lifetime even after a password change;
do not assume password rotation revokes them. Local PoP/username rotation may
require reprovisioning through vendor-supported procedures and is vendor-dependent.
Verify that old credentials no longer authenticate before resuming sharing.

There is no comprehensive automated leak detection or revocation here. The output
self-check only compares against credentials loaded by this process. Consider
separate secret scanning for the artifact directory before publication. Detection
and revocation response times are operator-dependent and unmeasured.

### Live Result, 2026-10-18

These historical runs executed commit
`5167a8af3841cfc4f76e6fd6bc10b2386c71786a`. The historical final-denial log does
not contain a source digest; it must not be used as source-hash evidence.

Read-only runs used existing account credentials from the homelab secret source,
first on pod `server0` (`10.42.1.31`) and then through existing SSH access to
physical `server0` (`172.16.1.128`). The physical host observed 54 mDNS service
types, including Home Assistant and other ESP devices, confirming multicast
visibility there. No `_esp_local_ctrl._tcp.local.` service appeared during the
20-second diagnostic browse or the independent service-type browse.

| Stage | ADU | Pool |
|---|---|---|
| Fresh cloud firmware | 5.4.7 | 5.4.7 |
| Local-control service metadata | Not advertised | Not advertised |
| Security / PoP / username | Unavailable / absent / absent | Unavailable / absent / absent |
| Matching local mDNS endpoint | Not found | Not found |
| Handshake / local identity / local properties | Not performed | Not performed |
| LED write / readback / restore | Not performed | Not performed |
| Process-scoped cloud denial | Verified, six blocked connects | Verified, same process |

Both cloud baselines reported brightness 75, hue 240, saturation 100, repellers
disabled, state/status 1, error 0, refill life 0. No live device writes were sent.
The precise remaining prerequisite is a hub exposing an enabled RainMaker local
service with account-provisioned security/credentials and a matching mDNS endpoint.
These observations do not prove that firmware can never support LAN control,
and do not demonstrate local protocol interoperability. No transport defect was
established by these traces, so the existing wire implementation is unchanged.
Artifacts are retained outside git at
`/data/projects/joyfulhouse/_artifacts/thermacell-lan-spike-20261018/`.

### Read-Only Rerun, 2026-10-19

After the tribunal fixes, both normal and cloud-denied reads executed commit
`d9eef09ebf812ae144fbaac8387fe7a45fbe06e2` on physical `server0`. Diagnostic
source SHA256: `e760bc0a793ca8992cb4a0b9e411fa074b343d15546cc6a17e0672c2de2c56e8`.
All 23 tracked runtime/dependency files were checked against the checkout before
execution. ADU and Pool still report firmware 5.4.7, no local-control metadata,
and no matching mDNS endpoint. Handshake, local identity, local properties, and
all LED stages remain `not_performed`. Both commands exit 2 for these missing
prerequisites. Cloud denial is verified with six blocked TCP connects; no live
device writes were requested or sent. The cloud LED baselines remain 75/240/100
(brightness/hue/saturation), with no changed/restored values.

The round-1 documentation commit `af16ff66b14b34545b64dde77595653692c80d6c`
uses this same diagnostic source. Its exact
checkout SHA and source digest are recorded separately in
`fix-r1/final-head-readonly.log` and `fix-r1/final-head-denial.log` under the
artifact directory, alongside per-hub JSON/text reports. These final-head runs
are also read-only. `LIVE-EVIDENCE.md` records the final checkout provenance and
distinguishes it from the historical runs.

Round-2 follow-up evidence is retained under `fix-r2/` in the same artifact
directory. Its `final-head-denial.log` records the executed checkout SHA and
imported diagnostic source hash for the read-only run with process cloud denial;
`LIVE-EVIDENCE.md` records the per-hub results.

### Offline Startup Assessment

- **Startup today:** normal client initialization authenticates to the cloud and
  discovers account nodes. This diagnostic also needs cloud bootstrap on every
  invocation. Neither securely persists local credentials or endpoints.
- **Runtime cloud outage:** already configured transports can read cached hubs
  directly; read failures may fall back to cloud. This remains simulator-tested
  for these hubs because no live local endpoint was available.
- **Offline restart:** not supported. A follow-up needs secure persistence of
  account-bound node identity, advertised security, PoP/username, and endpoint
  hints, plus a local-first startup path that does not require cloud login.
- **Address changes:** treat saved addresses as hints; rediscover using mDNS TXT
  identity and verify authenticated `config.node_id` before using a new endpoint.
  Never associate hubs by friendly name or address alone.
- **Credential rotation:** refresh local credentials from the authenticated
  account when available, invalidate failed credentials, and explicitly report
  that reprovisioning requires cloud access. Never downgrade advertised security.
- **Fallback semantics:** preserve cloud fallback for failed reads and explicit
  transport selection. Never replay an uncertain local write through cloud.
  Offline mode must surface unavailable cloud-only operations honestly.

First obtain firmware/provisioning evidence for an advertised local service and
repeat this spike, including LED restoration and denied-cloud local reads. Scope
secure persistence/local-first bootstrap as a separate change after that proof;
this PR does not implement offline bootstrap or alter HA startup.

## Refill Values

`refill_life` is a finite percentage in [0, 100], otherwise None.
`cartridge_present` is false for the app's `-1` missing-cartridge sentinel,
true for valid percentages (including zero), and None for unknown readings.
No percentages are clamped or fabricated from invalid data.
