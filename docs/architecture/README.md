# Architecture Documentation

System architecture and design patterns for pythermacell library.

---

## Documents

| Document | Description | Status |
|----------|-------------|--------|
| [AUTHENTICATION.md](AUTHENTICATION.md) | Authentication flow, JWT token management, session handling | ✅ Complete |
| [RESILIENCE.md](RESILIENCE.md) | Circuit breaker, exponential backoff, rate limiting patterns | ✅ Complete |

---

## Overview

### Authentication Architecture

**JWT-Based Authentication**:
- Authenticates with ESP RainMaker API via `/v1/login2`
- Returns `accesstoken` (for API requests) and `idtoken` (contains user metadata)
- User ID extracted from JWT token payload (`custom:user_id`)
- Tokens cached and reused across requests
- Automatic reauthentication on 401/403 responses

**Session Management**:
- Supports both session injection (Platinum tier) and owned sessions
- Session ownership tracking prevents improper cleanup
- Callback pattern for token synchronization
- Thread-safe with `asyncio.Lock`

See [AUTHENTICATION.md](AUTHENTICATION.md) for details.

### Resilience Architecture

**Three-Layer Resilience**:

1. **Circuit Breaker Pattern**
   - States: CLOSED (normal) → OPEN (failing) → HALF_OPEN (testing recovery)
   - Prevents cascading failures
   - Automatic recovery after timeout
   - Configurable thresholds

2. **Exponential Backoff**
   - Progressive retry delays: 1s → 2s → 4s → 8s...
   - Jitter to prevent thundering herd
   - Configurable max retries and delays
   - Works with authentication and API requests

3. **Rate Limiting**
   - Respects HTTP 429 (Too Many Requests)
   - Parses `Retry-After` header
   - Automatic retry with appropriate delay
   - Safety limits to prevent infinite waits

See [RESILIENCE.md](RESILIENCE.md) for details.

---

## Design Principles

### 1. Async-First
- All I/O operations use `async`/`await`
- No blocking operations
- Proper use of `asyncio.Lock` for thread safety
- Session management fully async

### 2. Type Safety
- Strict mypy configuration (`disallow_untyped_defs`)
- Complete type annotations (100%)
- TYPE_CHECKING imports for forward references
- Dataclass models for structured data

### 3. Resource Lifecycle
- Proper cleanup in `__aexit__`
- Cleanup on exceptions
- Session ownership tracking
- Context manager pattern throughout

### 4. Error Handling
- Custom exception hierarchy
- Exceptions with context attributes
- Proper error propagation
- User-friendly error messages

### 5. Testability
- Dependency injection (session, resilience components)
- Mock-friendly interfaces
- Comprehensive test coverage
- Integration tests with real API

---

## Module Organization

```
pythermacell/
├── auth.py           # AuthenticationHandler class
│   ├── authenticate()           # Main auth method
│   ├── force_reauthenticate()   # Force token refresh
│   ├── ensure_authenticated()   # Check and refresh if needed
│   └── _authenticate_attempt()  # Single auth attempt
│
├── client.py         # ThermacellClient class
│   ├── get_devices()            # Device discovery
│   ├── get_device()             # Get specific device
│   ├── get_device_state()       # Get device state
│   └── update_device_params()   # Control device
│
├── devices.py        # ThermacellDevice class
│   ├── turn_on() / turn_off()   # Power control
│   ├── set_led_color()          # LED control
│   ├── set_led_brightness()     # Brightness control
│   └── refresh()                # State refresh
│
├── resilience.py     # Resilience patterns
│   ├── CircuitBreaker           # Circuit breaker implementation
│   ├── ExponentialBackoff       # Backoff calculator
│   ├── RateLimiter              # Rate limit handler
│   └── retry_with_backoff()     # Combined retry logic
│
├── models.py         # Data models
│   ├── LoginResponse            # Auth response
│   ├── DeviceInfo               # Device info
│   ├── DeviceStatus             # Device status
│   ├── DeviceParams             # Device parameters
│   └── DeviceState              # Complete state
│
└── exceptions.py     # Custom exceptions
    ├── ThermacellError          # Base exception
    ├── AuthenticationError      # Auth failures
    ├── ThermacellConnectionError # Connection issues
    ├── ThermacellTimeoutError   # Timeouts
    ├── RateLimitError           # Rate limiting
    ├── DeviceError              # Device errors
    └── InvalidParameterError    # Parameter validation
```

---

## Component Interactions

### Authentication Flow
```
Client.__aenter__()
  ↓
AuthenticationHandler.__aenter__()
  ↓
authenticate()
  ↓
_authenticate_attempt()  (with retry logic)
  ↓
POST /v1/login2
  ↓
_decode_jwt_payload(idtoken)
  ↓
Extract user_id
  ↓
on_session_updated callback
```

### Device Discovery Flow
```
Client.get_devices()
  ↓
ensure_authenticated()
  ↓
GET /v1/user/nodes
  ↓
For each node:
  GET /v1/user/nodes/config
  GET /v1/user/nodes/status
  GET /v1/user/nodes/params
  ↓
_parse_device_*() methods
  ↓
Create DeviceState
  ↓
Create ThermacellDevice
  ↓
Return devices[]
```

### Device Control Flow
```
Device.turn_on()
  ↓
set_power(True)
  ↓
Client.update_device_params()
  ↓
_make_request(PUT, /user/nodes/params)
  ↓
retry_with_backoff() (optional)
  ↓
Circuit breaker check
  ↓
Rate limit check (if 429)
  ↓
Exponential backoff (if failure)
  ↓
Return success/failure
```

---

## Key Patterns

### Session Injection Pattern
```python
# Owned session (client creates and manages)
async with ThermacellClient(username, password) as client:
    # Client creates ClientSession, closes on exit
    ...

# Injected session (caller manages)
async with ClientSession() as session:
    async with ThermacellClient(username, password, session=session) as client:
        # Client uses session, doesn't close it
        ...
```

### Callback Pattern
```python
def on_token_updated(handler: AuthenticationHandler) -> None:
    # Sync tokens with other components
    print(f"New token: {handler.access_token}")

handler = AuthenticationHandler(
    username="...",
    password="...",
    on_session_updated=on_token_updated  # Called after auth
)
```

### Resilience Combination
```python
breaker = CircuitBreaker(failure_threshold=5)
backoff = ExponentialBackoff(max_retries=3)
limiter = RateLimiter()

client = ThermacellClient(
    username="...",
    password="...",
    circuit_breaker=breaker,
    backoff=backoff,
    rate_limiter=limiter
)

# All resilience patterns automatically applied
await client.get_devices()
```

---

## Performance Characteristics

### Typical Latencies
- Authentication: ~2.5 seconds
- Device discovery: ~1.5 seconds per device
- State retrieval: ~3 seconds (3 API calls)
- Control operation: ~2 seconds
- Token validation: <1ms (local)

### Resource Usage
- Memory: ~1MB per client instance
- Connections: 1 persistent HTTP/2 connection
- Tokens: ~2KB per session
- Circuit breaker: ~1KB state

### Scalability
- Concurrent clients: Tested up to 10
- Devices per client: No practical limit
- Requests per second: Limited by API rate limits
- Session lifetime: Hours (token expiration dependent)

---

## Security Considerations

### Credentials
- ✅ Credentials never logged
- ✅ Tokens stored in memory only
- ✅ SSL/TLS verification enabled
- ✅ No credential caching to disk

### Session Management
- ✅ Automatic token refresh
- ✅ Secure JWT token handling
- ✅ Proper session cleanup
- ✅ Thread-safe authentication

### API Security
- ✅ HTTPS only (no HTTP fallback)
- ✅ SSL certificate validation
- ✅ Authorization header for all requests
- ✅ Timeout protection

---

## Future Enhancements

See [../development/IMPROVEMENTS.md](../development/IMPROVEMENTS.md) for detailed roadmap.

### Planned
- OAuth 2.0 flow support
- Refresh token handling
- Multi-user session management
- Token persistence (optional)

### Under Consideration
- WebSocket support for real-time updates
- Local device discovery (mDNS)
- Device grouping
- Scheduled operations

---

## References

- [AUTHENTICATION.md](AUTHENTICATION.md) - Complete authentication documentation
- [RESILIENCE.md](RESILIENCE.md) - Complete resilience documentation
- [../api/openapi.yaml](../api/openapi.yaml) - API specification
- [../development/CODE_REVIEW_FEEDBACK.md](../development/CODE_REVIEW_FEEDBACK.md) - Code quality assessment
