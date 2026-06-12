import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.gemini_service import GeminiSession


@dataclass(frozen=True, slots=True)
class PendingVideo:
    data: bytes
    sequence: int


class InputScheduler:
    def __init__(self, audio_capacity: int):
        if audio_capacity <= 0:
            raise ValueError("audio_capacity must be positive")
        self._audio: asyncio.Queue[bytes] = asyncio.Queue(audio_capacity)
        self._text: asyncio.Queue[str] = asyncio.Queue()
        self._latest_video: PendingVideo | None = None
        self._wake = asyncio.Event()
        self._closed = False

    async def submit_audio(self, data: bytes) -> None:
        await self._audio.put(data)
        self._wake.set()

    async def submit_text(self, text: str) -> None:
        await self._text.put(text)
        self._wake.set()

    def submit_video(self, data: bytes, sequence: int) -> None:
        if (
            self._latest_video is None
            or sequence > self._latest_video.sequence
        ):
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
        self._wake.set()

    async def run(self, session: "GeminiSession") -> None:
        while True:
            self._wake.clear()

            while not self._text.empty():
                await session.send_text(self._text.get_nowait())
            while not self._audio.empty():
                await session.send_audio(self._audio.get_nowait())

            pending_video = self.take_latest_video()
            if pending_video is not None:
                await session.send_video_frame(pending_video[0])
                continue

            if self._closed:
                return

            await self._wake.wait()
