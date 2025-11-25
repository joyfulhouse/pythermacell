# Implementation Plan: Coalescing Request Queue

## Problem Statement

The Thermacell API and devices are sensitive to rapid successive calls. Too many frequent API calls cause:
1. API rate limiting (429 responses)
2. Device becoming unresponsive (requires physical reboot)
3. Integration test flakiness due to timing issues

## Solution: Intelligent Request Coalescing Queue

### Core Concept

Instead of immediately executing every API call, queue requests and intelligently coalesce them:
- **Power commands**: If `turn_on()` is pending and `turn_off()` is called, replace with just `turn_off()`
- **LED color/brightness**: Only the most recent color/brightness setting matters
- **Minimum delay**: Enforce minimum time between API calls (e.g., 500ms-1s)

### Architecture

```
User Calls → ThermacellDevice → CommandQueue → API
                                    ↓
                              Coalescing Logic
                                    ↓
                              Rate Limiting
                                    ↓
                              Single Execution
```

## Implementation Details

### 1. New Module: `src/pythermacell/queue.py`

```python
@dataclass
class QueuedCommand:
    """Represents a command waiting to be executed."""
    command_type: str  # "power", "led_brightness", "led_color", "refill_reset"
    params: dict[str, Any]
    future: asyncio.Future  # To return result to caller
    timestamp: datetime

class CommandQueue:
    """Coalescing command queue with rate limiting."""

    def __init__(
        self,
        min_interval: float = 0.5,  # Minimum 500ms between API calls
        max_queue_size: int = 10,
    ) -> None:
        self._queue: dict[str, QueuedCommand] = {}  # command_type -> latest command
        self._min_interval = min_interval
        self._last_execute_time: datetime | None = None
        self._lock = asyncio.Lock()
        self._processor_task: asyncio.Task | None = None

    async def enqueue(
        self,
        command_type: str,
        params: dict[str, Any],
        execute_fn: Callable[[], Awaitable[bool]],
    ) -> bool:
        """Add command to queue, replacing existing same-type command.

        If a command of the same type is already queued, it gets replaced
        (coalesced) with this new one. Only the most recent command executes.

        Returns:
            Result of the API call (True/False).
        """
        pass

    async def _process_queue(self) -> None:
        """Background task that processes queued commands."""
        pass

    async def flush(self) -> None:
        """Execute all pending commands immediately."""
        pass

    async def cancel(self, command_type: str) -> None:
        """Cancel a pending command of given type."""
        pass
```

### 2. Command Types and Coalescing Rules

| Command Type | Coalescing Behavior |
|--------------|---------------------|
| `power` | Replace: only final power state matters |
| `led_brightness` | Replace: only final brightness matters |
| `led_color` | Replace: only final color+brightness matters |
| `refill_reset` | No coalescing: each reset is intentional |

### 3. Integration with ThermacellDevice

Modify `devices.py` to use the queue:

```python
class ThermacellDevice:
    def __init__(self, api: ThermacellAPI, state: DeviceState) -> None:
        # ... existing code ...
        self._command_queue = CommandQueue(min_interval=0.5)

    async def set_power(self, power_on: bool) -> bool:
        # Optimistic update (unchanged)
        # ...

        # Queue the API call instead of direct execution
        async def execute():
            params = {DEVICE_TYPE_LIV_HUB: {"Enable Repellers": power_on}}
            return await self._update_params(params)

        return await self._command_queue.enqueue(
            command_type="power",
            params={"power_on": power_on},
            execute_fn=execute,
        )
```

### 4. Rate Limiting Constants

Add to `const.py`:

```python
# Request Queue Configuration
DEFAULT_MIN_REQUEST_INTERVAL = 0.5  # 500ms minimum between API calls
DEFAULT_COMMAND_TIMEOUT = 10.0  # Max time to wait for queued command
DEFAULT_MAX_QUEUE_SIZE = 10  # Maximum pending commands
```

### 5. Integration Test Improvements

Update tests to:
1. Use appropriate delays between operations (matching `DEFAULT_MIN_REQUEST_INTERVAL`)
2. Use the queue's `flush()` method before assertions
3. Increase timeout windows for state verification

## File Changes Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `src/pythermacell/queue.py` | NEW | Command queue with coalescing |
| `src/pythermacell/const.py` | EDIT | Add queue-related constants |
| `src/pythermacell/devices.py` | EDIT | Integrate queue into control methods |
| `src/pythermacell/__init__.py` | EDIT | Export CommandQueue |
| `tests/test_queue.py` | NEW | Unit tests for queue |
| `tests/integration/test_device_control_integration.py` | EDIT | Add delays between operations |

## Sequence Diagram

```
User          ThermacellDevice       CommandQueue            API
 │                 │                     │                    │
 │─turn_on()──────>│                     │                    │
 │                 │─enqueue("power")───>│                    │
 │                 │<─Future────────────│                    │
 │                 │                     │                    │
 │─turn_off()─────>│                     │                    │
 │                 │─enqueue("power")───>│ (replaces turn_on) │
 │                 │<─Future────────────│                    │
 │                 │                     │                    │
 │                 │                     │─(500ms delay)─────>│
 │                 │                     │─turn_off()────────>│
 │                 │                     │<─success──────────│
 │<─success───────│<─resolve Futures───│                    │
```

## Testing Strategy

1. **Unit Tests** (`test_queue.py`):
   - Test command coalescing (multiple same-type commands)
   - Test rate limiting (respects min_interval)
   - Test different command types don't interfere
   - Test flush() executes all pending
   - Test cancel() removes pending commands

2. **Integration Tests**:
   - Add `await asyncio.sleep(0.6)` between device operations
   - Use longer timeout windows for state verification
   - Test rapid-fire commands to verify coalescing works

## Migration Notes

- The queue is opt-in initially (backward compatible)
- Existing code continues to work without changes
- Users can enable queue behavior explicitly

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Queue grows unbounded | Max queue size limit |
| Commands never execute | Timeout on queued commands |
| User expects immediate execution | Optimistic updates still fire immediately |
| Race conditions | asyncio.Lock for thread safety |
