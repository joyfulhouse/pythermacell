# ADU native shutdown investigation

Tracking: [Thermacell LIV #30](https://github.com/joyfulhouse/thermacell_liv/issues/30),
homelab-1bjg. The firmware/cloud cause remains unresolved; no final promotion.

## Evidence

The earlier beta3 run failed native 20-second expiry on ADU: HTTP 200,
Enable Repellers=false, System State=2, System Status=2, Error=0. Verified
direct off also failed. An explicitly requested advertised LIV Hub.Reboot=true
with Enable Repellers=false recovered Off in about 21 seconds after removing
the test timer. Reboot is an operator recovery, not an automatic fix.

On the subsequent 2026-10-18 investigation, production still reported integration
2.1.0-beta.3 requiring pythermacell 0.3.0b3; both hubs reported firmware 5.4.7.
All 20 writable settings per hub matched the earlier failed-run baseline.
Neither hub advertised local control. Direct cloud GETs bypassed coordinator
and device caches; a second authenticated client independently checked expiry.

Both Pool and ADU reported the flag false and both operational codes 1 at 25,
40, and 65 seconds after native timer installation. Both also passed the exact
opt-in native-timer regression and actual HA run_for(minutes=1) expiry, followed
by a separate run_for/immediate-off/cancel sequence. No reboot was needed in
these repetitions. Native expiry disabled the schedule and reported command
source 7. Pool transiently reported Error=8 and ADU Error=72 during the broader
sequence despite operational Off; these raw bits are retained as observations,
not interpreted as proof of heater operation or a new diagnosed failure.

Passing repetitions do not invalidate the prior failure or establish a fix.
There is no evidence that increasing the polling window, changing timer/command
ordering, or automatically rebooting would resolve the underlying problem.
Without device-side telemetry, fresh cloud responses alone cannot separate stale
cloud reporting from firmware behavior or prove physical heater shutdown.

## Justified changes

- Library verified off now rejects absent/malformed operational status. The
  previous all([]) check accepted a false enable flag with no status fields.
- The hardware test gathers bounded settling evidence after native expiry
  failure, while retaining the original strict assertion. Logs allowlist only
  shutdown fields instead of dumping raw configuration and repeller identifiers.
- HA separately reconciles its remembered deadline after native expiry, makes
  one bounded verified off attempt, retains failure across restart, and raises
  a repair with new starts blocked until fresh operational Off. This addresses
  the demonstrated gap where disabled timers hid the deadline and the last on
  request hid the mismatch. It does not guarantee physical shutdown.

Raw snapshots, logs, JUnit results, service results, and restoration comparisons
are private local artifacts in thermacell-adu-shutdown-20261018. Publish only
redacted evidence. Capture current state before each run, pause and restore the
occupancy automation, retain native safeguards on failed cleanup, and verify
all writable parameters after removing test schedules. Never reset refill
counters as part of this regression.
