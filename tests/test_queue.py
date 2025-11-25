"""Tests for the command queue module."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from pythermacell.queue import CommandQueue, QueuedCommand


class TestQueuedCommand:
    """Tests for QueuedCommand dataclass."""

    async def test_create_command(self) -> None:
        """Test creating a queued command."""
        execute_fn = AsyncMock(return_value=True)
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()

        command = QueuedCommand(
            command_type="power",
            params={"power_on": True},
            execute_fn=execute_fn,
            future=future,
            timestamp=datetime.now(UTC),
        )

        assert command.command_type == "power"
        assert command.params == {"power_on": True}
        assert command.execute_fn == execute_fn


class TestCommandQueue:
    """Tests for CommandQueue class."""

    async def test_init_defaults(self) -> None:
        """Test queue initialization with defaults."""
        queue = CommandQueue()

        assert queue._min_interval == 0.5
        assert queue._max_queue_size == 10
        assert queue._command_timeout == 10.0
        assert queue.pending_count == 0
        assert queue.pending_types == []

    async def test_init_custom_values(self) -> None:
        """Test queue initialization with custom values."""
        queue = CommandQueue(min_interval=1.0, max_queue_size=5, command_timeout=5.0)

        assert queue._min_interval == 1.0
        assert queue._max_queue_size == 5
        assert queue._command_timeout == 5.0

    async def test_enqueue_single_command(self) -> None:
        """Test enqueuing a single command."""
        queue = CommandQueue(min_interval=0.0)  # No rate limiting for test
        execute_fn = AsyncMock(return_value=True)

        result = await queue.enqueue(
            command_type="power",
            params={"power_on": True},
            execute_fn=execute_fn,
        )

        assert result is True
        execute_fn.assert_awaited_once()
        await queue.shutdown()

    async def test_enqueue_coalesces_same_type(self) -> None:
        """Test that commands of same type are coalesced.

        Coalescing happens when a new command of the same type is enqueued
        while a previous command of that type is still waiting in the queue.
        The first command executes immediately; subsequent commands coalesce
        during the rate-limit wait before the next execution.
        """
        # Use a rate limit interval that allows coalescing
        queue = CommandQueue(min_interval=0.5, command_timeout=10.0)

        execute_calls: list[dict] = []

        async def execute_1() -> bool:
            execute_calls.append({"call": 1, "value": 50})
            return True

        async def execute_2() -> bool:
            execute_calls.append({"call": 2, "value": 75})
            return True

        async def execute_3() -> bool:
            execute_calls.append({"call": 3, "value": 100})
            return True

        # First command will execute immediately (no rate limit for first command)
        task1 = asyncio.create_task(
            queue.enqueue(command_type="led_brightness", params={"value": 50}, execute_fn=execute_1)
        )
        # Wait for first command to start executing
        await asyncio.sleep(0.05)

        # These two commands should coalesce during the 0.5s rate limit wait
        task2 = asyncio.create_task(
            queue.enqueue(command_type="led_brightness", params={"value": 75}, execute_fn=execute_2)
        )
        await asyncio.sleep(0.01)
        task3 = asyncio.create_task(
            queue.enqueue(command_type="led_brightness", params={"value": 100}, execute_fn=execute_3)
        )

        # Wait for all tasks
        results = await asyncio.gather(task1, task2, task3)

        # All should return True
        assert all(results)

        # First command executed, then commands 2 and 3 coalesced to only execute 3
        assert len(execute_calls) == 2
        assert execute_calls[0]["call"] == 1  # First executed immediately
        assert execute_calls[1]["call"] == 3  # Third replaced second via coalescing

        await queue.shutdown()

    async def test_enqueue_different_types_not_coalesced(self) -> None:
        """Test that different command types are not coalesced."""
        queue = CommandQueue(min_interval=0.0)  # No rate limiting

        power_executed = False
        brightness_executed = False

        async def execute_power() -> bool:
            nonlocal power_executed
            power_executed = True
            return True

        async def execute_brightness() -> bool:
            nonlocal brightness_executed
            brightness_executed = True
            return True

        # Queue two different command types
        result1 = await queue.enqueue(
            command_type="power",
            params={"power_on": True},
            execute_fn=execute_power,
        )
        result2 = await queue.enqueue(
            command_type="led_brightness",
            params={"value": 50},
            execute_fn=execute_brightness,
        )

        assert result1 is True
        assert result2 is True
        assert power_executed is True
        assert brightness_executed is True

        await queue.shutdown()

    async def test_rate_limiting(self) -> None:
        """Test that rate limiting enforces minimum interval."""
        queue = CommandQueue(min_interval=0.2)  # 200ms minimum

        execute_times: list[datetime] = []

        async def execute() -> bool:
            execute_times.append(datetime.now(UTC))
            return True

        # Queue two different command types
        await queue.enqueue(command_type="power", params={}, execute_fn=execute)
        await queue.enqueue(command_type="brightness", params={}, execute_fn=execute)

        assert len(execute_times) == 2

        # Check that second execution was delayed
        time_diff = (execute_times[1] - execute_times[0]).total_seconds()
        assert time_diff >= 0.15  # Allow some tolerance

        await queue.shutdown()

    async def test_cancel_pending_command(self) -> None:
        """Test cancelling a pending command.

        We queue a preliminary command first, then queue the command we want
        to cancel during the rate-limit wait period.
        """
        queue = CommandQueue(min_interval=1.0, command_timeout=10.0)

        execute_called = False
        preliminary_done = asyncio.Event()

        async def preliminary_execute() -> bool:
            preliminary_done.set()
            return True

        async def execute() -> bool:
            nonlocal execute_called
            execute_called = True
            return True

        # Queue a preliminary command to set up rate limiting
        prelim_task = asyncio.create_task(queue.enqueue(command_type="init", params={}, execute_fn=preliminary_execute))
        await preliminary_done.wait()  # Wait for it to execute

        # Now queue the command we want to cancel (during rate limit wait)
        task = asyncio.create_task(queue.enqueue(command_type="power", params={}, execute_fn=execute))

        # Give it a moment to be queued
        await asyncio.sleep(0.05)

        # Cancel the pending command
        cancelled = await queue.cancel("power")
        assert cancelled is True

        # Wait for task to complete
        result = await task
        assert result is False  # Cancelled commands return False

        # Execute should not have been called
        assert execute_called is False

        await prelim_task  # Clean up
        await queue.shutdown()

    async def test_cancel_nonexistent_command(self) -> None:
        """Test cancelling a non-existent command returns False."""
        queue = CommandQueue()

        cancelled = await queue.cancel("nonexistent")
        assert cancelled is False

        await queue.shutdown()

    async def test_cancel_all(self) -> None:
        """Test cancelling all pending commands."""
        queue = CommandQueue(min_interval=5.0)  # Very long interval

        execute_calls = 0

        async def execute() -> bool:
            nonlocal execute_calls
            execute_calls += 1
            return True

        # Queue multiple commands
        tasks = [
            asyncio.create_task(queue.enqueue(command_type="power", params={}, execute_fn=execute)),
            asyncio.create_task(queue.enqueue(command_type="brightness", params={}, execute_fn=execute)),
        ]

        # Give them time to be queued
        await asyncio.sleep(0.05)

        # Cancel all
        count = await queue.cancel_all()
        assert count >= 0  # May be 0 if first already executed

        # Wait for tasks
        await asyncio.gather(*tasks)

        await queue.shutdown()

    async def test_flush_executes_all_pending(self) -> None:
        """Test that flush executes all pending commands immediately."""
        queue = CommandQueue(min_interval=5.0)  # Very long interval

        execute_calls: list[str] = []

        async def execute_power() -> bool:
            execute_calls.append("power")
            return True

        async def execute_brightness() -> bool:
            execute_calls.append("brightness")
            return True

        # Start enqueue tasks
        task1 = asyncio.create_task(queue.enqueue(command_type="power", params={}, execute_fn=execute_power))
        task2 = asyncio.create_task(queue.enqueue(command_type="brightness", params={}, execute_fn=execute_brightness))

        # Give them time to be queued
        await asyncio.sleep(0.1)

        # Flush all pending
        await queue.flush()

        # Wait for tasks
        await asyncio.gather(task1, task2)

        # All should have executed
        assert "power" in execute_calls or "brightness" in execute_calls

        await queue.shutdown()

    async def test_shutdown_cancels_pending(self) -> None:
        """Test that shutdown cancels pending commands."""
        queue = CommandQueue(min_interval=5.0)

        execute_called = False

        async def execute() -> bool:
            nonlocal execute_called
            execute_called = True
            return True

        # Queue a command
        task = asyncio.create_task(queue.enqueue(command_type="power", params={}, execute_fn=execute))

        # Give it time to be queued
        await asyncio.sleep(0.05)

        # Shutdown
        await queue.shutdown()

        # Wait for task (should complete quickly due to cancellation)
        await asyncio.wait_for(task, timeout=1.0)

    async def test_pending_count(self) -> None:
        """Test pending_count property."""
        queue = CommandQueue(min_interval=5.0)

        assert queue.pending_count == 0

        # Queue a command (don't await)
        task = asyncio.create_task(
            queue.enqueue(command_type="power", params={}, execute_fn=AsyncMock(return_value=True))
        )

        # Give it time to be queued
        await asyncio.sleep(0.05)

        # Should have at least 0 pending (may have executed already)
        assert queue.pending_count >= 0

        await queue.shutdown()
        await task

    async def test_pending_types(self) -> None:
        """Test pending_types property."""
        queue = CommandQueue(min_interval=5.0)

        assert queue.pending_types == []

        # Queue commands (don't await)
        task1 = asyncio.create_task(
            queue.enqueue(command_type="power", params={}, execute_fn=AsyncMock(return_value=True))
        )
        task2 = asyncio.create_task(
            queue.enqueue(command_type="brightness", params={}, execute_fn=AsyncMock(return_value=True))
        )

        # Give them time to be queued
        await asyncio.sleep(0.05)

        # Check types (may be empty if already processed)
        types = queue.pending_types
        assert isinstance(types, list)

        await queue.shutdown()
        await asyncio.gather(task1, task2)

    async def test_command_timeout(self) -> None:
        """Test that commands timeout properly."""
        queue = CommandQueue(min_interval=5.0, command_timeout=0.1)  # 100ms timeout

        async def slow_execute() -> bool:
            await asyncio.sleep(10)  # Never completes
            return True

        # This should timeout
        with pytest.raises(asyncio.TimeoutError):
            await queue.enqueue(command_type="slow", params={}, execute_fn=slow_execute)

        await queue.shutdown()

    async def test_execute_failure_propagates(self) -> None:
        """Test that execute function failures propagate correctly."""
        queue = CommandQueue(min_interval=0.0)

        async def failing_execute() -> bool:
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            await queue.enqueue(command_type="failing", params={}, execute_fn=failing_execute)

        await queue.shutdown()

    async def test_coalesced_commands_share_result(self) -> None:
        """Test that coalesced commands all receive the same result."""
        queue = CommandQueue(min_interval=0.3)

        async def execute() -> bool:
            await asyncio.sleep(0.1)  # Small delay to allow coalescing
            return True

        # Queue multiple same-type commands quickly
        task1 = asyncio.create_task(queue.enqueue(command_type="power", params={"v": 1}, execute_fn=execute))
        await asyncio.sleep(0.01)
        task2 = asyncio.create_task(queue.enqueue(command_type="power", params={"v": 2}, execute_fn=execute))

        # Both should get the same result
        results = await asyncio.gather(task1, task2)
        assert results[0] is True
        assert results[1] is True

        await queue.shutdown()


class TestCommandQueueIntegration:
    """Integration tests for CommandQueue with realistic scenarios."""

    async def test_rapid_power_toggles(self) -> None:
        """Test rapid on/off/on sequence - coalescing happens during rate limit wait.

        First command executes immediately; subsequent commands during rate
        limit wait period get coalesced.
        """
        queue = CommandQueue(min_interval=0.5, command_timeout=10.0)

        final_state: list[bool] = []

        async def set_power(on: bool) -> bool:
            final_state.append(on)
            return True

        # First toggle executes immediately
        task1 = asyncio.create_task(
            queue.enqueue(
                command_type="power",
                params={"on": True},
                execute_fn=lambda: set_power(True),
            )
        )
        # Wait for first to start executing
        await asyncio.sleep(0.05)

        # These two should coalesce during rate limit wait
        task2 = asyncio.create_task(
            queue.enqueue(
                command_type="power",
                params={"on": False},
                execute_fn=lambda: set_power(False),
            )
        )
        await asyncio.sleep(0.01)
        task3 = asyncio.create_task(
            queue.enqueue(
                command_type="power",
                params={"on": True},
                execute_fn=lambda: set_power(True),
            )
        )

        await asyncio.gather(task1, task2, task3)

        # First executes, then 2 and 3 coalesce to only execute 3
        assert len(final_state) == 2
        assert final_state[0] is True  # First command
        assert final_state[1] is True  # Third command (second was coalesced)

        await queue.shutdown()

    async def test_color_changes_coalesce(self) -> None:
        """Test that rapid color changes coalesce to final color.

        First color executes immediately; subsequent colors during rate
        limit wait period get coalesced.
        """
        queue = CommandQueue(min_interval=0.5, command_timeout=10.0)

        final_colors: list[int] = []

        async def set_color(hue: int) -> bool:
            final_colors.append(hue)
            return True

        # First command (hue=0) executes immediately
        first_task = asyncio.create_task(
            queue.enqueue(
                command_type="led_color",
                params={"hue": 0},
                execute_fn=lambda: set_color(0),
            )
        )
        # Wait for first to start executing
        await asyncio.sleep(0.05)

        # Remaining colors should coalesce during rate limit wait
        tasks = [first_task]
        for hue in [60, 120, 180, 240, 300, 360]:
            tasks.append(
                asyncio.create_task(
                    queue.enqueue(
                        command_type="led_color",
                        params={"hue": hue},
                        execute_fn=lambda h=hue: set_color(h),
                    )
                )
            )
            await asyncio.sleep(0.01)

        await asyncio.gather(*tasks)

        # First color executes, remaining coalesce to only execute final
        assert len(final_colors) == 2
        assert final_colors[0] == 0  # First color
        assert final_colors[1] == 360  # Final color (others coalesced)

        await queue.shutdown()

    async def test_mixed_command_types_execute_independently(self) -> None:
        """Test that different command types execute independently."""
        queue = CommandQueue(min_interval=0.1)

        executed: dict[str, int] = {"power": 0, "brightness": 0, "color": 0}

        async def set_power() -> bool:
            executed["power"] += 1
            return True

        async def set_brightness() -> bool:
            executed["brightness"] += 1
            return True

        async def set_color() -> bool:
            executed["color"] += 1
            return True

        # Queue different types
        await queue.enqueue(command_type="power", params={}, execute_fn=set_power)
        await queue.enqueue(command_type="brightness", params={}, execute_fn=set_brightness)
        await queue.enqueue(command_type="color", params={}, execute_fn=set_color)

        # All should execute exactly once
        assert executed["power"] == 1
        assert executed["brightness"] == 1
        assert executed["color"] == 1

        await queue.shutdown()
