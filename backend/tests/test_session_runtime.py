import asyncio

import pytest

from app.services.session_runtime import (
    SessionIdleTimeout,
    SessionLifetimeExceeded,
    SessionRuntime,
)


def test_idle_expiration_raises_typed_exception():
    async def scenario():
        now = 100.0
        runtime = SessionRuntime(
            idle_seconds=45.0,
            max_seconds=600.0,
            clock=lambda: now,
        )
        now = 145.0

        with pytest.raises(SessionIdleTimeout):
            await runtime.wait_until_expired()

    asyncio.run(scenario())


def test_activity_refreshes_idle_deadline():
    async def scenario():
        now = 100.0
        runtime = SessionRuntime(
            idle_seconds=45.0,
            max_seconds=600.0,
            clock=lambda: now,
        )
        now = 130.0
        runtime.record_activity()
        now = 175.0

        with pytest.raises(SessionIdleTimeout):
            await runtime.wait_until_expired()

        assert runtime.last_activity == 130.0

    asyncio.run(scenario())


def test_max_lifetime_is_not_extended_by_activity():
    async def scenario():
        now = 100.0
        runtime = SessionRuntime(
            idle_seconds=45.0,
            max_seconds=60.0,
            clock=lambda: now,
        )
        now = 150.0
        runtime.record_activity()
        now = 160.0

        with pytest.raises(SessionLifetimeExceeded):
            await runtime.wait_until_expired()

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
