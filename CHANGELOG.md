# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.1] - 2026-10-23

First stable release of the 0.3 line. (Version 0.3.0 was never published:
PyPI permanently reserves that previously deleted filename.) This
release covers native services, verified power control, and experimental RainMaker LAN transport, consolidating 0.3.0b1-0.3.0b5.

### Fixed
- A rejected cloud reauthentication (`AuthenticationError`) during device
  discovery is no longer masked by cached membership when local transports are
  registered; it always propagates so callers can prompt for new credentials.

### Changed
- Bump cryptography to 50.0.2 (#74).
- LAN control is documented as **experimental**: it is validated only against
  HTTP/protocol simulators because no tested firmware (5.4.7) advertises local
  control. Offline startup remains unsupported (#76).

### Validated
- Native shutdown timers, verified power control, and bulk results on two live
  hubs (firmware 5.4.7): the opt-in native 20-second timer regression passed
  3/3 repetitions on each hub (2026-10-23), each confirming operational Off at
  expiry with no settling polls, followed by a verified timed run and verified
  off. No writable settings changed; no reboot was needed.

### Known Limitation
- Firmware 5.4.7 has intermittently reported Warming after native timer expiry
  while the enable flag is false (joyfulhouse/thermacell_liv#30). Verified off
  requires explicit integer operational Off evidence, so such reports fail
  confirmation instead of passing silently. Cloud reports cannot prove physical
  heater state, and the library never reboots a hub automatically.

## [0.3.0b5] - 2026-10-20

### Added
- Opt-in LAN diagnostic with independent discovery/authentication/identity/read
  reporting, redacted artifacts, process-scoped cloud denial, and an explicit
  LED brightness write mode with verified finally restoration (Refs #72).
- Document live firmware 5.4.7 results for ADU/Pool: no advertised local-control
  metadata or matching mDNS endpoint; no live local reads or writes claimed.

### Fixed
- Keep LED restoration shielded through repeated cancellation; always write the
  original brightness and verify it, including after HTTP/protocol errors that
  may follow a dispatched change. Verify even after a refused/failed restore
  write; failed restoration remains unconfirmed even with matching stale reads.
  Only a typed pre-dispatch read-only refusal permits unchanged-state confirmation.
- Refuse LED mutations when the snapshot contains a known credential and redact
  restoration failure alerts, including numeric proof-of-possession values.
- Fail closed on diagnostic output errors and known credential leaks; validate
  metadata, explain missing prerequisites safely, and summarize text artifacts.
- Preserve IPv6 interface scopes under process cloud denial and try alternative
  discovered addresses for reads without retrying writes on another endpoint.
- Preserve restoration-failure exit status across interrupts and report refusals;
  retain safe stage-status stubs. Remove private ID-token capture from the diagnostic.

## [0.3.0b4] - 2026-10-19

### Fixed
- Verified off requires an explicit integer operational Off report; missing or
  malformed status can no longer pass on a false enable flag alone.
- Native shutdown hardware regression collects bounded settling evidence after
  expiry failure and logs only allowlisted shutdown fields, preserving strict
  assertions and the native safeguard when cleanup cannot confirm shutdown.

### Known Limitation
- Firmware 5.4.7 can still report Warming after native timer expiry despite the
  enable flag being false. This beta strengthens confirmation and diagnostics;
  it does not establish physical shutdown or automatically reboot the hub (#30
  in joyfulhouse/thermacell_liv).

## [0.3.0b3] - 2026-10-18

### Fixed
- Preserve HTTP 207 bulk response arrays, including per-node success/failure
  descriptions, with HTTP contract coverage for successful and mixed batches (#69).
- Include reported power, operational state/status, and error codes in failed
  power-confirmation logs. Preserve strict failure for contradictory off reports.

### Tests
- Add an opt-in firmware 5.4.7 timed shutdown reproduction with raw recovery
  polling and verified cleanup. Hardware root cause remains under investigation
  (joyfulhouse/thermacell_liv#30).

## [0.3.0b2] - 2026-10-18

### Fixed
- Allow protobuf 7 so Home Assistant installations pinned to protobuf 7.36.0
  can install the native-control beta. Test the supported protobuf 5, 6, and 7
  runtime families in CI.

## [0.2.7] - 2026-10-18

### Fixed
- Match Android 4.0.5 device queries using `node_id` and discover the writable
  power parameter from config metadata.
- Add optional `set_power(..., verify=True)` confirmation against reported power
  and system status; restore optimistic state on errors and cancellation.
- Skip cancelled queued commands and propagate coalesced cancellation correctly.
- Handle JSON-typed bodyless 204 responses and reject non-integer refill codes.
- Run hardware integration tests only through explicit workflow dispatch; ordinary
  release and pull-request checks no longer toggle hubs or reset cartridge usage.

### Documentation
- Add the Android/refill audit and correct refill, LED-write, and runtime schemas.

## [0.2.6] - 2026-09-13

### Fixed
- `has_error` no longer reports the latching firmware 5.4.1 bit `0x00000040`
  as a fault on healthy hubs; the raw bitfield remains available via `.error`.
  (joyfulhouse/thermacell_liv#22)

## [0.2.5] - 2026-08-10

### Fixed
- `has_error` no longer reports benign bits of the `Error` bitfield as faults.
  Bits `0x01000000` (constantly set on some healthy hubs) and `0x00000008`
  (firmware 5.4.1 warm-up) are masked via `pythermacell.const.BENIGN_ERROR_BITS`;
  the raw bitfield remains available via `.error`. (#54)

## [0.2.4] - 2026-03-05

### Fixed
- **System Runtime conversion**: API returns values in tenths of hours (6-minute intervals), not minutes. Values are now correctly multiplied by 6 to produce accurate minute values (#24, contributed by @sjafferali)
- **Missing System Runtime preserves None**: When the API doesn't report System Runtime, the value is now correctly `None` instead of silently defaulting to `0`
- **CI integration tests for fork PRs**: Fork PRs now gracefully skip integration tests instead of failing (GitHub Actions doesn't pass secrets to forks)

### Changed
- Integration test conftest uses `pytest.skip()` instead of raising `ValueError` when credentials are missing
- CI workflow detects fork PRs and skips integration tests automatically

### Added
- GitHub Secrets configured on `integration-tests` environment for CI
- `SYSTEM_RUNTIME_MULTIPLIER` constant (value: 6) for runtime unit conversion
- 3 new test cases for System Runtime conversion (normal, zero, missing)

## [0.2.3] - 2025-11-25

### Fixed
- **Device name parsing**: User-friendly device names (e.g., "Pool", "ADU") are now correctly parsed from `params["LIV Hub"]["Name"]` instead of the generic device type from `config["info"]["name"]`
- Falls back to config name, then node_id if params name is not available

### Changed
- Integration tests are now less aggressive to avoid knocking devices offline:
  - Increased rate limit delay between tests (10s for control tests, 5s for regular)
  - `verify_state()` delay increased from 5s to 8s with 5s retry delay
  - Reduced `test_led_color_range` from 11 to 5 test iterations
  - All short delays (1-2s) increased to 5s minimum

### Added
- 3 new test cases for device name parsing fallback logic

## [0.2.2] - 2025-11-25

### Fixed
- Queue now handles event loop changes for reusable clients
- Sequential operations test properly verifies power state

### Added
- Coalescing command queue for intelligent request handling
- Retry logic to integration tests for CI reliability

## [0.1.0] - 2025-11-22

### Added
- Initial release of pythermacell library
- Core functionality:
  - Authentication with ESP RainMaker API
  - Device discovery and management
  - Device control (power, LED, parameters)
  - Three-layer architecture (API, Client, Device)
  - Optimistic updates for responsive UX
  - Auto-refresh and state change listeners
  - Resilience patterns (circuit breaker, exponential backoff, rate limiting)
- ThermacellClient class for high-level device management
- ThermacellAPI class for low-level HTTP operations
- ThermacellDevice class for stateful device representation
- AuthenticationHandler for JWT token management
- Session injection support for Home Assistant integration
- Comprehensive error handling with custom exceptions
- Type-safe implementation (100% mypy strict mode)
- Test coverage: 90.13%
- 212 comprehensive tests (161 unit, 51 integration)
- Documentation: README.md, CLAUDE.md, inline code comments, Google-style docstrings

### Technical Details
- Python 3.13+ support
- aiohttp for async HTTP operations
- ESP RainMaker API integration
- JWT token authentication with 4-hour lifetime
- Automatic token refresh on 401/403
- Rate limiting support (Retry-After header)
- Circuit breaker pattern for fault tolerance
- Exponential backoff with jitter for retries
- Optimistic updates with automatic rollback on failure
- Background auto-refresh with configurable intervals
- State change listener support for reactive programming

---

[Unreleased]: https://github.com/joyfulhouse/pythermacell/compare/v0.2.4...HEAD
[0.2.4]: https://github.com/joyfulhouse/pythermacell/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/joyfulhouse/pythermacell/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/joyfulhouse/pythermacell/compare/v0.1.0...v0.2.2
[0.1.0]: https://github.com/joyfulhouse/pythermacell/releases/tag/v0.1.0
