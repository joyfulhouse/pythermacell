"""Example showing session injection for Home Assistant integration."""

import asyncio

from aiohttp import ClientSession

from pythermacell import ThermacellClient


async def main() -> None:
    """Demonstrate session injection pattern for HA integration."""
    # This pattern is useful for Home Assistant integrations where
    # the session is managed by the application

    async with ClientSession() as session:
        print("Using application-managed aiohttp session")

        # Client will use the provided session instead of creating its own
        client = ThermacellClient(
            username="your@email.com",
            password="your_password",
            session=session,  # Inject existing session
        )

        async with client:
            devices = await client.get_devices()
            print(f"Found {len(devices)} device(s) using injected session")

            for device in devices:
                print(f"  - {device.name} ({device.node_id})")

        # Session remains open after client exits
        print("\nClient closed, but session still available for other requests")


async def home_assistant_style() -> None:
    """Example matching Home Assistant async_get_clientsession pattern."""
    # Simulating Home Assistant's session management
    app_session = ClientSession()  # In HA: async_get_clientsession(hass)

    try:
        client = ThermacellClient(
            username="your@email.com",
            password="your_password",
            session=app_session,
        )

        async with client:
            # Client uses HA's session, doesn't close it
            devices = await client.get_devices()
            print(f"Home Assistant pattern: {len(devices)} devices")

    finally:
        # Application manages session lifecycle
        await app_session.close()


if __name__ == "__main__":
    asyncio.run(main())
    asyncio.run(home_assistant_style())
