# Resilience Patterns

This document describes the resilience patterns available in pythermacell for building robust, fault-tolerant applications.

## Overview

The `pythermacell.resilience` module provides three core resilience patterns:

1. **Circuit Breaker**: Prevents cascading failures by temporarily blocking requests when errors exceed a threshold
2. **Exponential Backoff**: Implements progressive retry delays to avoid overwhelming failing services
3. **Rate Limiter**: Handles HTTP 429 (Too Many Requests) responses and respects `Retry-After` headers

These patterns can be used independently or combined for comprehensive fault tolerance.

## Circuit Breaker

### Overview

The circuit breaker pattern prevents cascading failures by monitoring operation failures and temporarily blocking requests when errors exceed a threshold.

### States

A circuit breaker can be in one of three states:

- **CLOSED** (normal operation): Requests are allowed through. Failures are counted.
- **OPEN** (blocking requests): Too many failures occurred. All requests are blocked.
- **HALF_OPEN** (testing recovery): After a timeout, limited requests are allowed to test if the service recovered.

### State Transitions

```
CLOSED --[failures ≥ threshold]--> OPEN
OPEN --[recovery timeout elapsed]--> HALF_OPEN
HALF_OPEN --[success count reached]--> CLOSED
HALF_OPEN --[any failure]--> OPEN
```

### Basic Usage

```python
from pythermacell.resilience import CircuitBreaker, CircuitState

# Create a circuit breaker
breaker = CircuitBreaker(
    failure_threshold=5,      # Open after 5 failures
    recovery_timeout=60.0,    # Try recovery after 60 seconds
    success_threshold=2,      # Need 2 successes to close from half-open
)

# Before making a request
if not breaker.can_execute():
    raise RuntimeError("Circuit breaker is open")

try:
    # Make your request
    result = await make_api_call()
    breaker.record_success()
    return result
except Exception as exc:
    breaker.record_failure(exc)
    raise
```

### Configuration

```python
CircuitBreaker(
    failure_threshold: int = 5,           # Failures before opening
    recovery_timeout: float = 60.0,       # Seconds before trying half-open
    success_threshold: int = 2,           # Successes needed to close
    monitored_exceptions: tuple = (Exception,)  # Which exceptions to monitor
)
```

### Monitoring Specific Exceptions

```python
from aiohttp import ClientError

# Only monitor network errors, ignore other exceptions
breaker = CircuitBreaker(
    failure_threshold=3,
    monitored_exceptions=(ClientError, TimeoutError)
)
```

### Checking State

```python
# Check current state
print(breaker.state)  # CircuitState.CLOSED, OPEN, or HALF_OPEN

# Check if requests are allowed
if breaker.can_execute():
    # Make request
    pass

# Manually reset the circuit breaker
breaker.reset()
```

## Exponential Backoff

### Overview

Exponential backoff implements progressive retry delays to avoid overwhelming a recovering service. Each retry waits longer than the previous one.

### Basic Usage

```python
from pythermacell.resilience import ExponentialBackoff

backoff = ExponentialBackoff(
    base_delay=1.0,        # Start with 1 second delay
    max_delay=60.0,        # Cap at 60 seconds
    max_retries=5,         # Try up to 5 times
    exponential_base=2.0,  # Double each time
    jitter=True           # Add randomness
)

for attempt in range(backoff.max_retries):
    try:
        result = await make_api_call()
        break  # Success
    except Exception:
        if attempt < backoff.max_retries - 1:
            delay = backoff.calculate_delay(attempt)
            await asyncio.sleep(delay)
        else:
            raise  # All retries exhausted
```

### Delay Calculation

Without jitter:
```
delay = base_delay × exponential_base^attempt
delay = min(delay, max_delay)
```

With jitter (recommended):
```
delay = random.uniform(0, calculated_delay)
```

### Configuration

```python
ExponentialBackoff(
    base_delay: float = 1.0,        # Initial delay in seconds
    max_delay: float = 60.0,        # Maximum delay in seconds
    max_retries: int = 5,           # Maximum retry attempts
    exponential_base: float = 2.0,  # Exponential growth factor
    jitter: bool = True            # Add random jitter (recommended)
)
```

### Why Jitter?

Jitter adds randomness to prevent the "thundering herd" problem where many clients retry simultaneously:

```python
# Without jitter - all clients retry at same time
backoff = ExponentialBackoff(jitter=False)
# Delays: 1.0s, 2.0s, 4.0s, 8.0s, 16.0s

# With jitter - clients retry at different times
backoff = ExponentialBackoff(jitter=True)
# Delays: 0.7s, 1.3s, 3.2s, 5.8s, 12.4s (randomized)
```

## Rate Limiter

### Overview

The rate limiter handles HTTP 429 (Too Many Requests) responses and respects the `Retry-After` header.

### Basic Usage

```python
from pythermacell.resilience import RateLimiter
from http import HTTPStatus

rate_limiter = RateLimiter(
    default_retry_delay=30.0,   # Default wait time
    max_retry_delay=300.0,      # Cap at 5 minutes
    respect_retry_after=True    # Honor server's Retry-After header
)

response = await session.get(url)

if RateLimiter.is_rate_limited(response.status):
    retry_after = response.headers.get("Retry-After")
    delay = rate_limiter.get_retry_delay(response.status, retry_after)
    await asyncio.sleep(delay)
    # Retry the request
```

### Configuration

```python
RateLimiter(
    default_retry_delay: float = 30.0,   # Used when no Retry-After header
    max_retry_delay: float = 300.0,      # Cap delay at this value
    respect_retry_after: bool = True     # Honor Retry-After header
)
```

### Retry-After Header Formats

The rate limiter parses integer seconds format:

```python
# Server says wait 60 seconds
response.headers["Retry-After"] = "60"
delay = rate_limiter.get_retry_delay(429, "60")  # Returns 60.0
```

HTTP date format is not currently supported (will fall back to default_retry_delay).

## Unified Retry Helper

### Overview

The `retry_with_backoff` function combines all three patterns into a single, easy-to-use helper.

### Basic Usage

```python
from pythermacell.resilience import retry_with_backoff, ExponentialBackoff

async def fetch_data():
    async with session.get(url) as response:
        return await response.json()

# Retry with exponential backoff
backoff = ExponentialBackoff(base_delay=1.0, max_retries=3)
result = await retry_with_backoff(
    fetch_data,
    backoff=backoff,
    retryable_exceptions=(ClientError,)
)
```

### Complete Example with All Patterns

```python
from pythermacell.resilience import (
    CircuitBreaker,
    ExponentialBackoff,
    RateLimiter,
    retry_with_backoff,
)
from http import HTTPStatus

# Configure resilience patterns
breaker = CircuitBreaker(failure_threshold=5)
backoff = ExponentialBackoff(base_delay=1.0, max_retries=5)
rate_limiter = RateLimiter()

async def make_request():
    async with session.get(url) as response:
        return response

# Use all patterns together
result = await retry_with_backoff(
    make_request,
    circuit_breaker=breaker,
    backoff=backoff,
    rate_limiter=rate_limiter,
    retryable_exceptions=(ClientError, TimeoutError),
    get_response_status=lambda r: r.status,
    get_retry_after=lambda r: r.headers.get("Retry-After"),
)
```

### Configuration

```python
retry_with_backoff(
    func: Callable,                           # Async function to execute
    circuit_breaker: CircuitBreaker | None,   # Optional circuit breaker
    backoff: ExponentialBackoff | None,       # Optional backoff strategy
    rate_limiter: RateLimiter | None,         # Optional rate limiter
    retryable_exceptions: tuple,              # Exceptions that trigger retry
    get_response_status: Callable | None,     # Extract status from response
    get_retry_after: Callable | None,         # Extract Retry-After header
)
```

## Integration with AuthenticationHandler

The `AuthenticationHandler` supports all resilience patterns through optional constructor parameters.

### Basic Authentication with Retry

```python
from pythermacell import AuthenticationHandler
from pythermacell.resilience import ExponentialBackoff

backoff = ExponentialBackoff(base_delay=1.0, max_retries=3)

async with AuthenticationHandler(
    username="user@example.com",
    password="password",
    backoff=backoff,
) as auth:
    await auth.authenticate()
    # Will retry up to 3 times on failure
```

### Authentication with Circuit Breaker

```python
from pythermacell import AuthenticationHandler
from pythermacell.resilience import CircuitBreaker

breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60)

async with AuthenticationHandler(
    username="user@example.com",
    password="password",
    circuit_breaker=breaker,
) as auth:
    try:
        await auth.authenticate()
    except RuntimeError as exc:
        if "Circuit breaker is open" in str(exc):
            # Circuit is open, wait before retrying
            await asyncio.sleep(60)
```

### Authentication with All Patterns

```python
from pythermacell import AuthenticationHandler
from pythermacell.resilience import CircuitBreaker, ExponentialBackoff, RateLimiter

breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)
backoff = ExponentialBackoff(base_delay=1.0, max_retries=5)
rate_limiter = RateLimiter()

async with AuthenticationHandler(
    username="user@example.com",
    password="password",
    circuit_breaker=breaker,
    backoff=backoff,
    rate_limiter=rate_limiter,
) as auth:
    await auth.authenticate()
    # Benefits from all three patterns:
    # - Retries with exponential backoff
    # - Circuit breaker prevents cascading failures
    # - Rate limiter respects 429 responses
```

## Best Practices

### 1. Use Jitter for Backoff

Always enable jitter to prevent thundering herd problems:

```python
# Good
backoff = ExponentialBackoff(jitter=True)

# Avoid (except for testing)
backoff = ExponentialBackoff(jitter=False)
```

### 2. Set Appropriate Thresholds

Circuit breaker thresholds should balance fault tolerance with responsiveness:

```python
# For critical services - fail fast
breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30)

# For resilient services - allow more failures
breaker = CircuitBreaker(failure_threshold=10, recovery_timeout=120)
```

### 3. Respect Rate Limits

Always configure rate limiter to respect server headers:

```python
# Good - respects server guidance
rate_limiter = RateLimiter(respect_retry_after=True)

# Avoid - may violate rate limits
rate_limiter = RateLimiter(respect_retry_after=False)
```

### 4. Monitor Specific Exceptions

Only monitor exceptions that indicate temporary failures:

```python
from aiohttp import ClientError

# Good - only monitor transient errors
breaker = CircuitBreaker(
    monitored_exceptions=(ClientError, TimeoutError)
)

# Avoid - monitors all exceptions including bugs
breaker = CircuitBreaker(
    monitored_exceptions=(Exception,)
)
```

### 5. Set Reasonable Retry Limits

Too many retries can cause cascading delays:

```python
# Good - reasonable retry count
backoff = ExponentialBackoff(max_retries=5)

# Avoid - too many retries
backoff = ExponentialBackoff(max_retries=20)
```

### 6. Cap Maximum Delays

Prevent unbounded waiting:

```python
# Good - capped at 1 minute
backoff = ExponentialBackoff(max_delay=60.0)

# Avoid - could wait hours
backoff = ExponentialBackoff(max_delay=3600.0)
```

## Testing

### Testing Circuit Breaker

```python
async def test_circuit_breaker():
    breaker = CircuitBreaker(failure_threshold=2)

    # Record failures to open circuit
    breaker.record_failure(Exception("error"))
    breaker.record_failure(Exception("error"))

    assert breaker.state == CircuitState.OPEN
    assert not breaker.can_execute()

    # Reset for testing
    breaker.reset()
    assert breaker.state == CircuitState.CLOSED
```

### Testing Exponential Backoff

```python
def test_exponential_backoff():
    backoff = ExponentialBackoff(
        base_delay=1.0,
        exponential_base=2.0,
        jitter=False  # Disable for predictable tests
    )

    assert backoff.calculate_delay(0) == 1.0
    assert backoff.calculate_delay(1) == 2.0
    assert backoff.calculate_delay(2) == 4.0
```

### Testing with Short Timeouts

Use small delays for faster tests:

```python
async def test_retry_with_backoff():
    backoff = ExponentialBackoff(base_delay=0.01, max_retries=3)

    call_count = 0
    async def failing_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("temporary failure")
        return "success"

    result = await retry_with_backoff(
        failing_func,
        backoff=backoff,
        retryable_exceptions=(ValueError,)
    )

    assert result == "success"
    assert call_count == 3
```

## Common Patterns

### Pattern 1: Graceful Degradation

```python
async def get_user_data(user_id: str) -> dict:
    """Get user data with fallback to cached version."""
    try:
        return await retry_with_backoff(
            lambda: api.get_user(user_id),
            backoff=ExponentialBackoff(max_retries=3),
            circuit_breaker=user_api_breaker,
        )
    except Exception:
        # Fall back to cached data
        return cache.get_user(user_id)
```

### Pattern 2: Progressive Timeout

```python
async def fetch_with_progressive_timeout(url: str):
    """Increase timeout with each retry."""
    backoff = ExponentialBackoff(base_delay=5.0, max_retries=3)

    for attempt in range(backoff.max_retries):
        timeout = 10 + (attempt * 5)  # 10s, 15s, 20s
        try:
            return await fetch_with_timeout(url, timeout)
        except TimeoutError:
            if attempt < backoff.max_retries - 1:
                await asyncio.sleep(backoff.calculate_delay(attempt))

    raise TimeoutError("All retries exhausted")
```

### Pattern 3: Shared Circuit Breaker

```python
# Share circuit breaker across multiple operations
api_breaker = CircuitBreaker(failure_threshold=10)

async def operation_a():
    if not api_breaker.can_execute():
        raise RuntimeError("API circuit breaker is open")
    # ... make request

async def operation_b():
    if not api_breaker.can_execute():
        raise RuntimeError("API circuit breaker is open")
    # ... make request
```

## Troubleshooting

### Circuit Breaker Not Opening

Check if you're recording failures:

```python
try:
    result = await make_request()
    breaker.record_success()
except Exception as exc:
    breaker.record_failure(exc)  # Don't forget this!
    raise
```

### Circuit Breaker Opens Too Quickly

Increase the failure threshold:

```python
# Before: Opens after 3 failures
breaker = CircuitBreaker(failure_threshold=3)

# After: Opens after 10 failures
breaker = CircuitBreaker(failure_threshold=10)
```

### Retries Happening Too Fast

Increase base delay:

```python
# Before: First retry after 1 second
backoff = ExponentialBackoff(base_delay=1.0)

# After: First retry after 5 seconds
backoff = ExponentialBackoff(base_delay=5.0)
```

### Rate Limiting Not Working

Ensure you're passing the Retry-After header:

```python
response = await session.get(url)
retry_after = response.headers.get("Retry-After")  # Must extract header
delay = rate_limiter.get_retry_delay(response.status, retry_after)
```

## Performance Considerations

### Circuit Breaker Overhead

Minimal - just a few integer comparisons and timestamp checks.

### Backoff Calculation

Very fast - simple exponential calculation with optional random number generation.

### Thread Safety

All patterns are designed for asyncio and are safe for concurrent use within a single event loop. For multi-threaded applications, use separate instances per thread.

## API Reference

See module docstrings for complete API documentation:

```python
from pythermacell import resilience
help(resilience.CircuitBreaker)
help(resilience.ExponentialBackoff)
help(resilience.RateLimiter)
help(resilience.retry_with_backoff)
```

## Further Reading

- [Release It!](https://pragprog.com/titles/mnee2/release-it-second-edition/) by Michael Nygard
- [AWS Architecture Blog: Exponential Backoff and Jitter](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/)
- [Martin Fowler: Circuit Breaker](https://martinfowler.com/bliki/CircuitBreaker.html)
