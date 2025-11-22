"""Basic device control example for pythermacell.

This example demonstrates:
- Authenticating with the Thermacell API
- Discovering devices
- Controlling device power
- Setting LED colors
"""

import asyncio
import logging

from pythermacell import ThermacellClient


# Configure logging to see what's happening
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


async def main() -> None:
    """Main example function."""
    # Replace with your credentials
    username = "your@email.com"
    password = "your_password"

    print("Connecting to Thermacell API...")

    async with ThermacellClient(username=username, password=password) as client:
        # Get all devices
        print("\nDiscovering devices...")
        devices = await client.get_devices()

        if not devices:
            print("No devices found. Make sure you have Thermacell devices registered.")
            return

        print(f"Found {len(devices)} device(s)\n")

        # Work with the first device
        device = devices[0]

        # Display device information
        print(f"Device: {device.name}")
        print(f"  Model: {device.model}")
        print(f"  Firmware: {device.firmware_version}")
        print(f"  Serial: {device.serial_number}")
        print(f"  Online: {device.is_online}")
        print(f"  Powered: {device.is_powered_on}")
        print()

        # Turn on the device
        print("Turning device ON...")
        success = await device.turn_on()
        if success:
            print("  ✓ Device turned on successfully")
        else:
            print("  ✗ Failed to turn on device")
            return

        # Wait a moment
        await asyncio.sleep(2)

        # Set LED to green
        print("\nSetting LED to GREEN...")
        success = await device.set_led_color(
            hue=120,        # Green
            saturation=100,  # Full saturation
            brightness=80    # 80% brightness
        )
        if success:
            print("  ✓ LED color set successfully")
        else:
            print("  ✗ Failed to set LED color")

        # Refresh device state to see changes
        await asyncio.sleep(2)
        await device.refresh()

        # Display current state
        print("\nCurrent Device State:")
        print(f"  Power: {'ON' if device.is_powered_on else 'OFF'}")
        print(f"  LED Power: {'ON' if device.led_power else 'OFF'}")
        print(f"  LED Brightness: {device.led_brightness}%")
        print(f"  LED Hue: {device.led_hue}° (Green ≈ 120°)")
        print(f"  LED Saturation: {device.led_saturation}%")
        print(f"  Refill Life: {device.refill_life}%")
        print(f"  Runtime: {device.system_runtime} minutes")


if __name__ == "__main__":
    asyncio.run(main())
