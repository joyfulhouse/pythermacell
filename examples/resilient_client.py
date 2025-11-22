"""Resilient client example with circuit breaker and retry logic.

This example demonstrates:
- Circuit breaker pattern for fault tolerance
- Exponential backoff for retries
- Rate limiting support
- Comprehensive error handling
"""

import asyncio
import logging

from pythermacell import (
    AuthenticationError,
    ThermacellClient,
    ThermacellConnectionError,
    ThermacellTimeoutError,
)
from pythermacell.resilience import CircuitBreaker, CircuitState, ExponentialBackoff, RateLimiter


# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


async def main() -> None:
    """Main example function with resilience patterns."""
    # Replace with your credentials
    username = "your@email.com"
    password = "your_password"

    # Configure resilience patterns
    print("Configuring resilience patterns...\n")

    # Circuit Breaker: Prevents cascading failures
    breaker = CircuitBreaker(
        failure_threshold=3,   # Open circuit after 3 failures
        recovery_timeout=30.0,  # Wait 30 seconds before testing recovery
        success_threshold=2     # Require 2 successes to close circuit
    )
    print(f"Circuit Breaker: threshold={breaker.config.failure_threshold}, " \
          f"recovery={breaker.config.recovery_timeout}s")

    # Exponential Backoff: Progressive retry delays
    backoff = ExponentialBackoff(
        base_delay=1.0,         # Start with 1 second
        max_delay=30.0,         # Max 30 seconds
        max_retries=5,          # Up to 5 retries
        exponential_base=2.0,   # Double each time
        jitter=True             # Add randomness
    )
    print(f"Exponential Backoff: base={backoff.config.base_delay}s, " \
          f"max={backoff.config.max_delay}s, retries={backoff.config.max_retries}")

    # Rate Limiter: Handles HTTP 429 responses
    limiter = RateLimiter(
        respect_retry_after=True,
        default_retry_delay=60.0,
        max_retry_delay=300.0
    )
    print(f"Rate Limiter: default_delay={limiter.config.default_retry_delay}s, " \
          f"max={limiter.config.max_retry_delay}s\n")

    # Create client with all resilience patterns
    client = ThermacellClient(
        username=username,
        password=password,
        circuit_breaker=breaker,
        backoff=backoff,
        rate_limiter=limiter
    )

    try:
        async with client:
            print("Connecting to Thermacell API...")
            print(f"Circuit State: {breaker.state.value}\n")

            # Get devices - this will automatically:
            # - Retry on failure with exponential backoff
            # - Open circuit if too many failures
            # - Respect rate limiting
            devices = await client.get_devices()

            print(f"✓ Successfully retrieved {len(devices)} device(s)")
            print(f"Circuit State: {breaker.state.value}")
            print(f"Failure Count: {breaker.failure_count}")

            if not devices:
                print("\nNo devices found.")
                return

            # Display device information
            print("\nDevices:")
            for i, device in enumerate(devices, 1):
                print(f"  {i}. {device.name} ({device.model})")
                print(f"     Online: {device.is_online}")
                print(f"     Powered: {device.is_powered_on}")
                print(f"     Refill: {device.refill_life}%")

            # Test circuit breaker recovery
            print("\n" + "="*50)
            print("Circuit Breaker Status:")
            print(f"  State: {breaker.state.value}")
            print(f"  Failures: {breaker.failure_count}/{breaker.config.failure_threshold}")
            print(f"  Successes: {breaker.success_count}")

            if breaker.state == CircuitState.OPEN:
                print("\n⚠️  Circuit is OPEN - requests are blocked")
                print(f"   Will retry in {breaker.config.recovery_timeout} seconds")
            elif breaker.state == CircuitState.HALF_OPEN:
                print("\n🔄 Circuit is HALF-OPEN - testing recovery")
            else:
                print("\n✓ Circuit is CLOSED - normal operation")

    except AuthenticationError as e:
        print(f"\n❌ Authentication failed: {e}")
        print("   Check your username and password")

    except ThermacellTimeoutError as e:
        print(f"\n❌ Request timed out: {e}")
        print("   Network may be slow or service unavailable")

    except ThermacellConnectionError as e:
        print(f"\n❌ Connection error: {e}")
        print("   Check your internet connection")

    except RuntimeError as e:
        if "circuit breaker" in str(e).lower():
            print(f"\n❌ Circuit breaker is open: {e}")
            print(f"   Breaker state: {breaker.state.value}")
            print(f"   Failures: {breaker.failure_count}")
            print(f"   Wait {breaker.config.recovery_timeout}s before retry")
        else:
            raise

    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        raise

    finally:
        # Display final circuit breaker state
        print("\n" + "="*50)
        print("Final Circuit Breaker State:")
        print(f"  State: {breaker.state.value}")
        print(f"  Total Failures: {breaker.failure_count}")


if __name__ == "__main__":
    asyncio.run(main())
