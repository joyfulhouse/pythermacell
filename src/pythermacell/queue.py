"""Coalescing command queue with rate limiting for Thermacell devices.

This module provides intelligent request queuing that:
- Coalesces duplicate commands (e.g., multiple power toggles → single final state)
- Enforces minimum interval between API calls to prevent device overload
- Provides async-compatible interface with proper cancellation support
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pythermacell.const import (
    DEFAULT_COMMAND_TIMEOUT,
    DEFAULT_MAX_QUEUE_SIZE,
    DEFAULT_MIN_REQUEST_INTERVAL,
)


if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

_LOGGER = logging.getLogger(__name__)


@dataclass
class QueuedCommand:
    """Represents a command waiting to be executed.

    Attributes:
        command_type: Category of command (power, led_brightness, led_color, etc.)
        params: Command parameters for logging/debugging
        execute_fn: Async function to execute when command is processed
        future: Future to resolve when command completes
        timestamp: When the command was queued
    """

    command_type: str
    params: dict[str, Any]
    execute_fn: Callable[[], Awaitable[bool]]
    future: asyncio.Future[bool] = field(default_factory=lambda: asyncio.get_event_loop().create_future())
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class CommandQueue:
    """Coalescing command queue with rate limiting.

    This queue intelligently handles rapid command sequences by:
    1. **Coalescing**: If a command of the same type is already queued, it gets
       replaced with the new one. Only the most recent command executes.
    2. **Rate Limiting**: Enforces minimum time between API calls to prevent
       overwhelming the device or API.
    3. **Async-First**: Returns futures that resolve when commands complete,
       allowing callers to await results.

    Example:
        ```python
        queue = CommandQueue(min_interval=0.5)

        # These will coalesce - only brightness=100 will execute
        await queue.enqueue("led_brightness", {"value": 50}, set_brightness_50)
        await queue.enqueue("led_brightness", {"value": 75}, set_brightness_75)
        result = await queue.enqueue("led_brightness", {"value": 100}, set_brightness_100)

        # Different command types don't interfere
        await queue.enqueue("power", {"on": True}, turn_on)
        await queue.enqueue("led_brightness", {"value": 50}, set_brightness_50)
        ```

    Attributes:
        min_interval: Minimum seconds between API calls.
        max_queue_size: Maximum pending commands per type.
    """

    def __init__(
        self,
        min_interval: float = DEFAULT_MIN_REQUEST_INTERVAL,
        max_queue_size: int = DEFAULT_MAX_QUEUE_SIZE,
        command_timeout: float = DEFAULT_COMMAND_TIMEOUT,
    ) -> None:
        """Initialize the command queue.

        Args:
            min_interval: Minimum seconds between API calls.
            max_queue_size: Maximum pending commands (unused currently, reserved for future).
            command_timeout: Maximum seconds to wait for a queued command to complete.
        """
        self._min_interval = min_interval
        self._max_queue_size = max_queue_size
        self._command_timeout = command_timeout

        # Command type -> latest queued command
        self._queue: dict[str, QueuedCommand] = {}

        # Execution state
        self._last_execute_time: datetime | None = None
        # Lock and event are created lazily to ensure they're bound to the correct event loop
        self._lock: asyncio.Lock | None = None
        self._processor_task: asyncio.Task[None] | None = None
        self._processing_event: asyncio.Event | None = None
        self._shutdown = False

    @property
    def pending_count(self) -> int:
        """Get number of pending commands."""
        return len(self._queue)

    @property
    def pending_types(self) -> list[str]:
        """Get list of pending command types."""
        return list(self._queue.keys())

    async def enqueue(
        self,
        command_type: str,
        params: dict[str, Any],
        execute_fn: Callable[[], Awaitable[bool]],
    ) -> bool:
        """Add command to queue, replacing existing same-type command.

        If a command of the same type is already queued, it gets replaced
        (coalesced) with this new one. Only the most recent command executes.

        The caller should still perform optimistic updates before calling this,
        as the actual API call may be delayed.

        Args:
            command_type: Category of command (e.g., "power", "led_brightness").
            params: Command parameters (for logging/debugging only).
            execute_fn: Async function to execute when command is processed.

        Returns:
            Result of the API call (True/False) when it eventually executes.

        Raises:
            asyncio.TimeoutError: If command doesn't complete within timeout.
        """
        # Ensure processor is running (creates lock/event if needed for current event loop)
        self._ensure_processor_running()

        # Now lock and event are guaranteed to exist
        assert self._lock is not None
        assert self._processing_event is not None

        async with self._lock:
            # Check for existing command of same type to coalesce
            old_cmd_to_chain: QueuedCommand | None = None
            if command_type in self._queue:
                old_command = self._queue[command_type]
                if not old_command.future.done():
                    _LOGGER.debug(
                        "Coalescing %s command: %s -> %s",
                        command_type,
                        old_command.params,
                        params,
                    )
                    old_cmd_to_chain = old_command

            # Create new command
            loop = asyncio.get_running_loop()
            future: asyncio.Future[bool] = loop.create_future()

            command = QueuedCommand(
                command_type=command_type,
                params=params,
                execute_fn=execute_fn,
                future=future,
                timestamp=datetime.now(UTC),
            )

            # Handle coalescing: chain old future to new one
            if old_cmd_to_chain is not None:
                # Capture the old future before creating callback
                captured_old_future = old_cmd_to_chain.future

                # When new future completes, resolve old one with same result
                def chain_result(
                    f: asyncio.Future[bool],
                    old_future: asyncio.Future[bool] = captured_old_future,
                ) -> None:
                    if not old_future.done():
                        if f.exception():
                            old_future.set_exception(f.exception())  # type: ignore[arg-type]
                        else:
                            old_future.set_result(f.result())

                future.add_done_callback(chain_result)

            self._queue[command_type] = command
            _LOGGER.debug("Queued %s command: %s", command_type, params)

            # Signal processor that new work is available
            self._processing_event.set()

        # Wait for result with timeout
        try:
            return await asyncio.wait_for(future, timeout=self._command_timeout)
        except TimeoutError:
            _LOGGER.warning("Command %s timed out after %ss", command_type, self._command_timeout)
            raise

    def _ensure_processor_running(self) -> None:
        """Ensure the background processor task is running."""
        if self._processor_task is None or self._processor_task.done():
            # Reset shutdown flag if previously shutdown (allows queue reuse)
            self._shutdown = False
            # Create new lock and event bound to current event loop
            # (needed when queue is reused across different event loops in tests)
            self._lock = asyncio.Lock()
            self._processing_event = asyncio.Event()
            self._processor_task = asyncio.create_task(self._process_queue())

    async def _process_queue(self) -> None:
        """Background task that processes queued commands with rate limiting."""
        _LOGGER.debug("Command queue processor started")

        # These are guaranteed to be set by _ensure_processor_running before this task starts
        assert self._processing_event is not None
        assert self._lock is not None

        try:
            while not self._shutdown:
                # Wait for work or shutdown
                try:
                    await asyncio.wait_for(self._processing_event.wait(), timeout=1.0)
                except TimeoutError:
                    # Check for shutdown periodically
                    continue

                self._processing_event.clear()

                # Process all pending commands
                while self._queue:
                    # Rate limiting: wait if needed
                    await self._wait_for_rate_limit()

                    # Get next command to process
                    async with self._lock:
                        if not self._queue:
                            break

                        # Process commands in order they were queued
                        # (using dict order preservation in Python 3.7+)
                        command_type = next(iter(self._queue))
                        command = self._queue.pop(command_type)

                    # Execute command outside lock
                    await self._execute_command(command)

        except asyncio.CancelledError:
            _LOGGER.debug("Command queue processor cancelled")
            raise
        finally:
            _LOGGER.debug("Command queue processor stopped")

    async def _wait_for_rate_limit(self) -> None:
        """Wait until rate limit allows next execution."""
        if self._last_execute_time is not None:
            elapsed = (datetime.now(UTC) - self._last_execute_time).total_seconds()
            if elapsed < self._min_interval:
                wait_time = self._min_interval - elapsed
                _LOGGER.debug("Rate limiting: waiting %.3fs", wait_time)
                await asyncio.sleep(wait_time)

    async def _execute_command(self, command: QueuedCommand) -> None:
        """Execute a single command and resolve its future."""
        try:
            _LOGGER.debug("Executing %s command: %s", command.command_type, command.params)
            result = await command.execute_fn()
            self._last_execute_time = datetime.now(UTC)

            if not command.future.done():
                command.future.set_result(result)

            _LOGGER.debug("Command %s completed: %s", command.command_type, result)

        except Exception as exc:
            _LOGGER.exception("Command %s failed", command.command_type)
            if not command.future.done():
                command.future.set_exception(exc)

    async def flush(self) -> None:
        """Execute all pending commands immediately, ignoring rate limits.

        This is useful for cleanup or when you need to ensure all pending
        operations complete before continuing.
        """
        if self._lock is None:
            # No commands have been enqueued yet, nothing to flush
            return

        async with self._lock:
            commands = list(self._queue.values())
            self._queue.clear()

        for command in commands:
            await self._execute_command(command)

    async def cancel(self, command_type: str) -> bool:
        """Cancel a pending command of given type.

        Args:
            command_type: The command type to cancel.

        Returns:
            True if a command was cancelled, False if none was pending.
        """
        if self._lock is None:
            # No commands have been enqueued yet
            return False

        async with self._lock:
            if command_type in self._queue:
                command = self._queue.pop(command_type)
                if not command.future.done():
                    command.future.set_result(False)
                _LOGGER.debug("Cancelled %s command", command_type)
                return True
            return False

    async def cancel_all(self) -> int:
        """Cancel all pending commands.

        Returns:
            Number of commands cancelled.
        """
        if self._lock is None:
            # No commands have been enqueued yet
            return 0

        async with self._lock:
            count = len(self._queue)
            for command in self._queue.values():
                if not command.future.done():
                    command.future.set_result(False)
            self._queue.clear()
            _LOGGER.debug("Cancelled %d commands", count)
            return count

    async def shutdown(self) -> None:
        """Shutdown the queue processor.

        Cancels any pending commands and stops the background task.
        """
        self._shutdown = True
        if self._processing_event is not None:
            self._processing_event.set()  # Wake up processor

        await self.cancel_all()

        if self._processor_task is not None:
            self._processor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._processor_task
            self._processor_task = None

        _LOGGER.debug("Command queue shutdown complete")
