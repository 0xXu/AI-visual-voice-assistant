import asyncio
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.gemini_service import GeminiSession


class SchedulerClosed(RuntimeError):
    """The input scheduler no longer accepts work."""


class VideoSubmission(Enum):
    ACCEPTED = "accepted"
    REPLACED = "replaced"
    REJECTED = "rejected"


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
        self._audio: deque[bytes] = deque()
        self._text: deque[str] = deque()
        self._audio_capacity = audio_capacity
        self._text_capacity = text_capacity
        self._condition = asyncio.Condition()
        self._latest_video: PendingVideo | None = None
        self._highest_seen_video_sequence: int | None = None
        self._wake = asyncio.Event()
        self._closed = False

    async def submit_audio(self, data: bytes) -> None:
        await self._submit(self._audio, self._audio_capacity, data)

    async def submit_text(self, text: str) -> None:
        await self._submit(self._text, self._text_capacity, text)

    def submit_video(self, data: bytes, sequence: int) -> VideoSubmission:
        self._raise_if_closed()
        if (
            self._highest_seen_video_sequence is None
            or sequence > self._highest_seen_video_sequence
        ):
            replaced = self._latest_video is not None
            self._highest_seen_video_sequence = sequence
            self._latest_video = PendingVideo(data, sequence)
            self._wake.set()
            if replaced:
                return VideoSubmission.REPLACED
            return VideoSubmission.ACCEPTED
        return VideoSubmission.REJECTED

    async def take_audio(self) -> bytes:
        async with self._condition:
            while not self._audio and not self._closed:
                await self._condition.wait()
            if not self._audio:
                raise SchedulerClosed("input scheduler is closed")
            audio = self._audio.popleft()
            self._condition.notify_all()
            return audio

    def take_latest_video(self) -> tuple[bytes, int] | None:
        if self._latest_video is None:
            return None
        pending = self._latest_video
        self._latest_video = None
        return pending.data, pending.sequence

    async def close(self) -> None:
        async with self._condition:
            self._closed = True
            self._condition.notify_all()
        self._wake.set()

    async def run(self, session: "GeminiSession") -> None:
        while True:
            self._wake.clear()

            for _ in range(self._TEXT_BATCH_SIZE):
                text = await self._take_nowait(self._text)
                if text is None:
                    break
                await session.send_text(text)

            for _ in range(self._AUDIO_BATCH_SIZE):
                audio = await self._take_nowait(self._audio)
                if audio is None:
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

    async def _submit(
        self,
        queue: deque[bytes] | deque[str],
        capacity: int,
        item: bytes | str,
    ) -> None:
        async with self._condition:
            while len(queue) >= capacity and not self._closed:
                await self._condition.wait()
            self._raise_if_closed()
            queue.append(item)
        self._wake.set()

    async def _take_nowait(
        self,
        queue: deque[bytes] | deque[str],
    ) -> bytes | str | None:
        async with self._condition:
            if not queue:
                return None
            item = queue.popleft()
            self._condition.notify_all()
            return item

    def _raise_if_closed(self) -> None:
        if self._closed:
            raise SchedulerClosed("input scheduler is closed")

    def _has_pending_work(self) -> bool:
        return (
            bool(self._text)
            or bool(self._audio)
            or self._latest_video is not None
        )
