"""Monitor multiple Thermacell devices example.

This example demonstrates:
- Monitoring multiple devices
- Checking refill status
- Displaying device health information
- Alert on low refill
"""

import asyncio
from datetime import datetime

from pythermacell import ThermacellClient


async def monitor_device(device) -> dict:
    """Monitor a single device and return its status.

    Args:
        device: ThermacellDevice instance to monitor.

    Returns:
        Dictionary with device status information.
    """
    # Refresh to get latest state
    await device.refresh()

    # Calculate status
    status = "Online" if device.is_online else "Offline"
    power = "ON" if device.is_powered_on else "OFF"

    # Determine system state
    if device.system_status == 1:
        state = "Off"
    elif device.system_status == 2:
        state = "Warming Up"
    elif device.system_status == 3:
        state = "Protected"
    else:
        state = f"Unknown ({device.system_status})"

    # Check for alerts
    alerts = []
    if device.refill_life is not None and device.refill_life < 20:
        alerts.append(f"LOW REFILL ({device.refill_life}%)")

    if device.has_error:
        alerts.append(f"ERROR CODE {device.error}")

    if not device.is_online:
        alerts.append("OFFLINE")

    return {
        "name": device.name,
        "model": device.model,
        "status": status,
        "power": power,
        "state": state,
        "refill_life": device.refill_life,
        "runtime": device.system_runtime,
        "alerts": alerts,
    }


async def display_status(devices: list, status_data: list) -> None:
    """Display formatted status for all devices.

    Args:
        devices: List of ThermacellDevice instances.
        status_data: List of status dictionaries from monitor_device().
    """
    print(f"\n{'='*70}")
    print(f"Thermacell Device Monitor - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")

    for i, data in enumerate(status_data):
        print(f"Device {i+1}: {data['name']}")
        print(f"  Model:      {data['model']}")
        print(f"  Status:     {data['status']}")
        print(f"  Power:      {data['power']}")
        print(f"  State:      {data['state']}")
        print(f"  Refill:     {data['refill_life']}%" if data["refill_life"] is not None else "  Refill:     N/A")
        print(f"  Runtime:    {data['runtime']} min" if data["runtime"] is not None else "  Runtime:    N/A")

        if data["alerts"]:
            print(f"  ⚠️  ALERTS:  {', '.join(data['alerts'])}")

        print()


async def main() -> None:
    """Main monitoring function."""
    # Replace with your credentials
    username = "your@email.com"
    password = "your_password"

    async with ThermacellClient(username=username, password=password) as client:
        # Get all devices
        devices = await client.get_devices()

        if not devices:
            print("No devices found.")
            return

        print(f"Monitoring {len(devices)} device(s)...")
        print("Press Ctrl+C to stop\n")

        try:
            # Monitor loop (update every 30 seconds)
            while True:
                # Monitor all devices concurrently
                status_tasks = [monitor_device(device) for device in devices]
                status_data = await asyncio.gather(*status_tasks)

                # Display results
                display_status(devices, status_data)

                # Wait before next update
                print("Updating in 30 seconds... (Press Ctrl+C to stop)")
                await asyncio.sleep(30)

        except KeyboardInterrupt:
            print("\n\nMonitoring stopped by user.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")
