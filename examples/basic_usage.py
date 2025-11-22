"""Basic usage example for pythermacell library."""

import asyncio

from pythermacell import ThermacellClient


async def main() -> None:
    """Demonstrate basic usage of pythermacell."""
    # Initialize client with credentials
    async with ThermacellClient(
        username="your@email.com",
        password="your_password",
    ) as client:
        print("Connected to Thermacell API")

        # Get all devices
        devices = await client.get_devices()
        print(f"Found {len(devices)} device(s)")

        for device in devices:
            print(f"\nDevice: {device.name}")
            print(f"  Node ID: {device.node_id}")
            print(f"  Model: {device.model}")
            print(f"  Firmware: {device.firmware_version}")
            print(f"  Serial: {device.serial_number}")
            print(f"  Online: {device.is_online}")
            print(f"  Powered: {device.is_powered_on}")

            if device.is_online:
                # Device control
                print("\nTurning device on...")
                await device.turn_on()

                print("Setting LED color (green, 50% brightness)...")
                await device.set_led_color(hue=120, saturation=100, brightness=50)

                # Check refill life
                if device.refill_life is not None:
                    print(f"Refill life: {device.refill_life}%")

                # Refresh device state
                print("\nRefreshing device state...")
                await device.refresh()

                print(f"Current power state: {device.power}")
                print(f"LED brightness: {device.led_brightness}")


if __name__ == "__main__":
    asyncio.run(main())
