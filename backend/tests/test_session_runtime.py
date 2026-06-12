import asyncio

import pytest

from app.services.session_runtime import (
    SessionIdleTimeout,
    SessionLifetimeExceeded,
    SessionRuntime,
)


def test_idle_expiration_raises_typed_exception():
    async def scenario():
        runtime = SessionRuntime(
            idle_seconds=0.01,
            max_seconds=1.0,
        )

        with pytest.raises(SessionIdleTimeout):
            await runtime.wait_until_expired()

    asyncio.run(scenario())


def test_activity_refreshes_idle_deadline():
    async def scenario():
        runtime = SessionRuntime(
            idle_seconds=0.03,
            max_seconds=1.0,
        )
        waiter = asyncio.create_task(runtime.wait_until_expired())

        await asyncio.sleep(0.02)
        runtime.record_activity()
        await asyncio.sleep(0.02)
        assert not waiter.done()

        with pytest.raises(SessionIdleTimeout):
            await waiter

    asyncio.run(scenario())


def test_max_lifetime_is_not_extended_by_activity():
    async def scenario():
        runtime = SessionRuntime(
            idle_seconds=0.05,
            max_seconds=0.06,
        )
        waiter = asyncio.create_task(runtime.wait_until_expired())

        await asyncio.sleep(0.04)
        runtime.record_activity()

        with pytest.raises(SessionLifetimeExceeded):
            await waiter

        assert runtime.last_activity > runtime.started_at

    asyncio.run(scenario())


def test_wait_until_expired_is_cancellation_safe():
    async def scenario():
        runtime = SessionRuntime(idle_seconds=30.0, max_seconds=60.0)
        waiter = asyncio.create_task(runtime.wait_until_expired())

        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter

    asyncio.run(scenario())
