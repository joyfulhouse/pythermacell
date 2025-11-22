"""Example showing resilience patterns with pythermacell."""

import asyncio

from pythermacell import ThermacellClient
from pythermacell.resilience import CircuitBreaker, ExponentialBackoff, RateLimiter


async def main() -> None:
    """Demonstrate resilience patterns for production use."""
    # Configure resilience patterns
    circuit_breaker = CircuitBreaker(
        failure_threshold=5,  # Open circuit after 5 consecutive failures
        recovery_timeout=60.0,  # Wait 60 seconds before retry
        success_threshold=2,  # Require 2 successes to close circuit
    )

    backoff = ExponentialBackoff(
        base_delay=1.0,  # Start with 1 second delay
        max_delay=60.0,  # Cap at 60 seconds
        max_retries=5,  # Maximum 5 retry attempts
        jitter=True,  # Add randomness to prevent thundering herd
    )

    rate_limiter = RateLimiter(
        respect_retry_after=True,  # Honor Retry-After headers
        default_retry_delay=60.0,  # Default 60s if no header
        max_retry_delay=300.0,  # Cap at 5 minutes
    )

    # Create client with resilience patterns
    async with ThermacellClient(
        username="your@email.com",
        password="your_password",
        circuit_breaker=circuit_breaker,
        backoff=backoff,
        rate_limiter=rate_limiter,
    ) as client:
        print("Client configured with resilience patterns:")
        print("  - Circuit breaker for fault tolerance")
        print("  - Exponential backoff for retries")
        print("  - Rate limiting with Retry-After support")

        try:
            devices = await client.get_devices()
            print(f"\nSuccessfully retrieved {len(devices)} device(s)")

            for device in devices:
                # Operations are automatically protected by resilience patterns
                await device.turn_on()
                print(f"Turned on: {device.name}")

        except RuntimeError as e:
            if "Circuit breaker" in str(e):
                print("\nCircuit breaker is open - too many failures")
                print("Waiting for recovery timeout before retrying")
            else:
                raise


if __name__ == "__main__":
    asyncio.run(main())
