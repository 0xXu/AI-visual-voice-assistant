import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.gemini_service import GeminiSession


class SchedulerClosed(RuntimeError):
    """The input scheduler no longer accepts work."""


@dataclass(frozen=True, slots=True)
class PendingVideo:
    data: bytes
    sequence: int


class InputScheduler:
    _TEXT_BATCH_SIZE = 1
    _AUDIO_BATCH_SIZE = 8

    def __init__(self, audio_capacity: int, text_capacity: int = 8):
        if audio_capacity <= 0:
            raise ValueError("audio_capacity must be positive")
        if text_capacity <= 0:
            raise ValueError("text_capacity must be positive")
        self._audio: asyncio.Queue[bytes] = asyncio.Queue(audio_capacity)
        self._text: asyncio.Queue[str] = asyncio.Queue(text_capacity)
        self._latest_video: PendingVideo | None = None
        self._highest_seen_video_sequence: int | None = None
        self._wake = asyncio.Event()
        self._closed_event = asyncio.Event()
        self._closed = False

    async def submit_audio(self, data: bytes) -> None:
        await self._put_unless_closed(self._audio, data)
        self._wake.set()

    async def submit_text(self, text: str) -> None:
        await self._put_unless_closed(self._text, text)
        self._wake.set()

    def submit_video(self, data: bytes, sequence: int) -> None:
        self._raise_if_closed()
        if (
            self._highest_seen_video_sequence is None
            or sequence > self._highest_seen_video_sequence
        ):
            self._highest_seen_video_sequence = sequence
            self._latest_video = PendingVideo(data, sequence)
            self._wake.set()

    async def take_audio(self) -> bytes:
        return await self._audio.get()

    def take_latest_video(self) -> tuple[bytes, int] | None:
        if self._latest_video is None:
            return None
        pending = self._latest_video
        self._latest_video = None
        return pending.data, pending.sequence

    async def close(self) -> None:
        self._closed = True
        self._closed_event.set()
        self._wake.set()

    async def run(self, session: "GeminiSession") -> None:
        while True:
            self._wake.clear()

            for _ in range(self._TEXT_BATCH_SIZE):
                try:
                    text = self._text.get_nowait()
                except asyncio.QueueEmpty:
                    break
                await session.send_text(text)

            for _ in range(self._AUDIO_BATCH_SIZE):
                try:
                    audio = self._audio.get_nowait()
                except asyncio.QueueEmpty:
                    break
                await session.send_audio(audio)

            pending_video = self.take_latest_video()
            if pending_video is not None:
                await session.send_video_frame(pending_video[0])

            if self._closed and not self._has_pending_work():
                return

            if self._has_pending_work():
                continue

            await self._wake.wait()

    async def _put_unless_closed(
        self,
        queue: asyncio.Queue[bytes] | asyncio.Queue[str],
        item: bytes | str,
    ) -> None:
        self._raise_if_closed()
        try:
            queue.put_nowait(item)
            return
        except asyncio.QueueFull:
            pass

        put_task = asyncio.create_task(queue.put(item))
        close_task = asyncio.create_task(self._closed_event.wait())
        try:
            done, _ = await asyncio.wait(
                {put_task, close_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if put_task in done:
                await put_task
                return
            raise SchedulerClosed("input scheduler is closed")
        finally:
            for task in (put_task, close_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(
                put_task,
                close_task,
                return_exceptions=True,
            )

    def _raise_if_closed(self) -> None:
        if self._closed:
            raise SchedulerClosed("input scheduler is closed")

    def _has_pending_work(self) -> bool:
        return (
            not self._text.empty()
            or not self._audio.empty()
            or self._latest_video is not None
        )
