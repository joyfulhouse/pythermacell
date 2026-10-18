# OTA Firmware API

**Category**: API Reference
**Last Updated**: 2026-10-18
**Evidence**: LIV Android 4.0.5 `ApiManager$64`, `$65`, `$66` and `FwUpdateActivity`.

Requests use the account access token in `Authorization`.

| Method | Path | Query/body |
|---|---|---|
| GET | `/v1/user/nodes/ota_update` | Query `node_id` |
| POST | `/v1/user/nodes/ota_update` | JSON `node_id`, `ota_job_id` |
| GET | `/v1/user/nodes/ota_status` | Query `node_id`, `ota_job_id` |

The offer response contains `ota_available`, `fw_version`, `ota_job_id`,
`description`, `status`, and optionally `file_size`. Status responses contain
`status`, `additional_info`, and `timestamp`. `ota_details` in the app is an
internal Android Bundle key, not an extra JSON response wrapper.

The app recognizes stages `triggered`, `started`, `in-progress`, `completed`, `success`,
`failed`, `rejected`, and `unknown`. The wire spelling is `in-progress`, not
`in_progress`; completion is `completed` or `success`. The implemented API does not provide
an authoritative numeric progress percentage. HA exposes busy state and the
reported stage/details without inventing a percentage.

```python
update = await device.services.check_firmware()
if update.available:
    # Run only when the user requests installation.
    await device.services.install_firmware(update)
    await device.services.refresh_firmware_status(update)
```

Installation uses an offered job ID. Arbitrary image uploads, downgrade URLs,
firmware distribution links, and device provisioning are outside this API.
Offers, job acceptance, and status requests are covered by aiohttp contract tests;
physical installation has not been tested on a live hub for this release.

See [native services](NATIVE_SERVICES.md) for capability and transport behavior.
