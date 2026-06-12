import time
from collections.abc import Callable
from dataclasses import dataclass, field

from google.genai import types


@dataclass(slots=True)
class SessionUsage:
    token_budget: int
    clock: Callable[[], float] = time.monotonic
    audio_bytes: int = 0
    text_chars: int = 0
    video_frames: int = 0
    video_replaced_frames: int = 0
    video_bytes: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    _started_at: float = field(init=False, repr=False)
    _first_input_at: float | None = field(default=None, init=False, repr=False)
    _first_response_at: float | None = field(
        default=None,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if self.token_budget <= 0:
            raise ValueError("token_budget must be positive")
        self._started_at = self.clock()

    def record_audio(self, data: bytes) -> None:
        self.audio_bytes += len(data)
        self._record_input()

    def record_text(self, text: str) -> None:
        self.text_chars += len(text)
        self._record_input()

    def record_video(self, data: bytes, *, replaced: bool) -> None:
        self.video_frames += 1
        self.video_bytes += len(data)
        if replaced:
            self.video_replaced_frames += 1
        self._record_input()

    def record_gemini_usage(self, metadata: types.UsageMetadata) -> None:
        self.input_tokens += metadata.prompt_token_count or 0
        self.output_tokens += metadata.response_token_count or 0
        self.total_tokens += metadata.total_token_count or 0

    def record_response(self) -> None:
        if self._first_input_at is None or self._first_response_at is not None:
            return
        self._first_response_at = self.clock()

    @property
    def budget_exceeded(self) -> bool:
        return self.total_tokens >= self.token_budget

    def to_dict(self) -> dict[str, int | None]:
        duration_ms = round((self.clock() - self._started_at) * 1_000)
        latency_ms = None
        if (
            self._first_input_at is not None
            and self._first_response_at is not None
        ):
            latency_ms = round(
                (self._first_response_at - self._first_input_at) * 1_000
            )
        return {
            "audio_bytes": self.audio_bytes,
            "text_chars": self.text_chars,
            "video_frames": self.video_frames,
            "video_replaced_frames": self.video_replaced_frames,
            "video_bytes": self.video_bytes,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "duration_ms": duration_ms,
            "first_response_latency_ms": latency_ms,
        }

    def _record_input(self) -> None:
        if self._first_input_at is None:
            self._first_input_at = self.clock()
