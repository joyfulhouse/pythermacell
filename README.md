# pythermacell

A modern, fully-typed async Python client for Thermacell IoT devices (LIV Hub) built on the ESP RainMaker API.

[![PyPI Version][pypi-shield]][pypi]
[![Python Versions][pyversions-shield]][pypi]
[![License][license-shield]](LICENSE)
[![CI][ci-shield]][ci]
[![GitHub Sponsors][sponsors-shield]][sponsors]
[![Ko-fi][kofi-shield]][kofi]

## What It Does

`pythermacell` is an asynchronous Python library for controlling and monitoring
Thermacell LIV mosquito-repellent devices through their cloud platform (Espressif
ESP RainMaker). It handles authentication, device discovery, power and LED
control, and status monitoring behind a clean, fully-typed API. It is the engine
behind the [Thermacell LIV](https://github.com/joyfulhouse/thermacell_liv) Home
Assistant integration, and is equally suitable for standalone scripts and other
applications.

## Features

- Fully asynchronous (`aiohttp`) with comprehensive type hints (strict mypy).
- Three-layer architecture: low-level API, coordinating client, stateful devices.
- Power control, RGB LED control (HSV), and refill/runtime/status monitoring.
- Optimistic updates with automatic rollback for instant UI responsiveness.
- State caching, optional background auto-refresh, and change listeners.
- Built-in resilience: circuit breaker, exponential backoff, and rate limiting.
- Session injection for sharing an `aiohttp` session (e.g. with Home Assistant).
- Custom exception hierarchy and high unit + integration test coverage.

## Installation

See **[INSTALL.md](INSTALL.md)** for the complete guide.

```bash
pip install pythermacell
# or
uv add pythermacell
```

Requires Python 3.13+.

## Quick Start

```python
import asyncio

from pythermacell import ThermacellClient


async def main() -> None:
    async with ThermacellClient(
        username="your@email.com",
        password="your_password",
    ) as client:
        for device in await client.get_devices():
            print(f"{device.name} ({device.model}) online={device.is_online}")

            await device.turn_on()
            await device.set_led_color(hue=120, saturation=100, brightness=80)

            print(f"Refill life: {device.refill_life}%")


asyncio.run(main())
```

## Usage

The most common workflow is: construct a `ThermacellClient`, enter its async
context, fetch devices, then control or monitor them through `ThermacellDevice`
objects. Device control methods apply optimistically (local state updates
immediately, then the API call runs in the background and rolls back on failure).

```python
device = (await client.get_devices())[0]

await device.turn_on()                              # power on (optimistic)
await device.set_led_color(hue=240, saturation=100, brightness=80)  # blue
await device.refresh()                              # pull latest state from API

print(device.is_powered_on, device.refill_life, device.system_status)
```

For depth — authentication, LED rules, monitoring, optimistic updates,
auto-refresh and change listeners, session injection, resilience patterns, and
full error handling — see the **[Usage Guide](docs/USAGE.md)**. Runnable scripts
live in [`examples/`](examples/).

## API Reference

Full reference lives in [docs/](docs/README.md). Key entry points:

| Symbol | Description |
|---|---|
| [`ThermacellClient`](docs/USAGE.md#thermacellclient) | High-level client: authentication, device discovery, caching |
| [`ThermacellDevice`](docs/USAGE.md#thermacelldevice) | Stateful device: power, LED, monitoring, listeners |
| [`ThermacellAPI`](docs/USAGE.md#thermacellapi) | Low-level ESP RainMaker HTTP layer |
| [`AuthenticationHandler`](docs/architecture/AUTHENTICATION.md) | JWT authentication and token refresh |
| `pythermacell.resilience` | [Circuit breaker, backoff, rate limiter](docs/architecture/RESILIENCE.md) |
| [Exceptions](docs/USAGE.md#error-handling) | `ThermacellError` hierarchy |

Endpoint-level details are documented under [docs/api/](docs/api/README.md).

## Development

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md). In short:

```bash
git clone https://github.com/joyfulhouse/pythermacell.git
cd pythermacell
uv sync
uv run pytest
uv run ruff check
uv run mypy
```

## Support

- **Issues:** <https://github.com/joyfulhouse/pythermacell/issues>
- **PyPI:** <https://pypi.org/project/pythermacell/>

## Support Development

If this library is useful to you, please consider supporting its development:

- [GitHub Sponsors][sponsors]
- [Ko-fi][kofi]

## License

This project is licensed under the **MIT** License — see [LICENSE](LICENSE) for
details.

This is an unofficial library and is not affiliated with, endorsed by, or
sponsored by Thermacell Repellents, Inc. All product names, logos, and brands are
the property of their respective owners.

## Related Projects

- [Thermacell LIV](https://github.com/joyfulhouse/thermacell_liv) — the Home
  Assistant integration built on this library.

<!-- Badge links -->
[pypi-shield]: https://img.shields.io/pypi/v/pythermacell.svg?style=for-the-badge
[pypi]: https://pypi.org/project/pythermacell/
[pyversions-shield]: https://img.shields.io/pypi/pyversions/pythermacell.svg?style=for-the-badge
[license-shield]: https://img.shields.io/github/license/joyfulhouse/pythermacell.svg?style=for-the-badge
[ci-shield]: https://img.shields.io/github/actions/workflow/status/joyfulhouse/pythermacell/ci.yml?style=for-the-badge&label=CI
[ci]: https://github.com/joyfulhouse/pythermacell/actions
[sponsors-shield]: https://img.shields.io/badge/sponsor-GitHub-EA4AAA.svg?style=for-the-badge&logo=githubsponsors&logoColor=white
[sponsors]: https://github.com/sponsors/btli
[kofi-shield]: https://img.shields.io/badge/Ko--fi-donate-FF5E5B.svg?style=for-the-badge&logo=ko-fi&logoColor=white
[kofi]: https://ko-fi.com/bryanli
