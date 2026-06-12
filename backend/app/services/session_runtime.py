import asyncio
import time
from collections.abc import Callable


class SessionIdleTimeout(TimeoutError):
    """The session received no accepted user activity before its deadline."""


class SessionLifetimeExceeded(TimeoutError):
    """The session reached its fixed maximum lifetime."""


class SessionRuntime:
    def __init__(
        self,
        idle_seconds: float,
        max_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if idle_seconds <= 0:
            raise ValueError("idle_seconds must be positive")
        if max_seconds <= 0:
            raise ValueError("max_seconds must be positive")

        self.idle_seconds = idle_seconds
        self.max_seconds = max_seconds
        self._clock = clock
        self.started_at = clock()
        self.last_activity = self.started_at
        self._activity = asyncio.Event()

    def record_activity(self) -> None:
        self.last_activity = self._clock()
        self._activity.set()

    async def wait_until_expired(self) -> None:
        while True:
            self._activity.clear()
            now = self._clock()
            idle_deadline = self.last_activity + self.idle_seconds
            max_deadline = self.started_at + self.max_seconds

            if max_deadline <= now and max_deadline <= idle_deadline:
                raise SessionLifetimeExceeded
            if idle_deadline <= now:
                raise SessionIdleTimeout
            if max_deadline <= now:
                raise SessionLifetimeExceeded

            timeout = min(idle_deadline, max_deadline) - now
            try:
                await asyncio.wait_for(self._activity.wait(), timeout)
            except TimeoutError:
                continue
