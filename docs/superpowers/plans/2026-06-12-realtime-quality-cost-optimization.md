# Real-Time Quality And Cost Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve visual freshness and accuracy, reduce conversational latency, support natural interruption, and place enforceable limits around Gemini Live session cost.

**Architecture:** Keep the FastAPI server-to-server proxy, but stop forwarding every client message directly to Gemini. Introduce a bounded priority scheduler, an explicit session lifecycle, structured usage events, and Live API session-management options; keep frame-change detection and audio chunk formation on the client so unnecessary media never reaches the backend.

**Tech Stack:** Python 3.11, FastAPI, asyncio, Google Gen AI SDK 2.x, Pydantic Settings, pytest, TypeScript, React 19, Next.js 16, Vitest.

---

## File Structure

### Backend

- `backend/app/api/messages.py`: Parse lifecycle messages and timestamped media metadata.
- `backend/app/api/websocket.py`: Own the browser WebSocket and explicit start/stop lifecycle.
- `backend/app/core/config.py`: Store queue, timeout, budget, media, and session-management limits.
- `backend/app/services/input_scheduler.py`: Prioritize text/audio and retain only the newest video frame.
- `backend/app/services/session_runtime.py`: Enforce idle timeout, maximum duration, and token budget.
- `backend/app/services/gemini_service.py`: Configure Gemini Live and translate server events into application events.
- `backend/app/services/usage.py`: Aggregate bytes, frames, tokens, and latency metrics.
- `backend/tests/`: Unit and integration-style tests using fake Gemini sessions.

### Frontend

- `frontend/lib/audio.ts`: Convert microphone samples into 20–40 ms PCM chunks.
- `frontend/lib/framePolicy.ts`: Decide whether a frame is fresh and visually different enough to upload.
- `frontend/hooks/useAudioPlayer.ts`: Stop and clear queued playback when the user interrupts.
- `frontend/hooks/useWebSocket.ts`: Send lifecycle messages and timestamped video metadata.
- `frontend/app/page.tsx`: Start cloud sessions only after user action and use adaptive frame sampling.
- `frontend/vitest.config.ts`: Run pure TypeScript policy tests.

---

### Task 1: Add Explicit Session And Timestamped Media Protocol

**Files:**
- Modify: `backend/app/api/messages.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`
- Modify: `backend/tests/test_messages.py`
- Modify: `backend/tests/test_config.py`

- [ ] **Step 1: Write failing tests for lifecycle messages, audio size, JPEG validation, and stale-frame metadata**

Add to `backend/tests/test_messages.py`:

```python
def test_parses_session_lifecycle_messages(settings):
    assert parse_client_message(
        json.dumps({"type": "start_session", "data": ""}),
        settings,
    ).type == "start_session"
    assert parse_client_message(
        json.dumps({"type": "stop_session", "data": ""}),
        settings,
    ).type == "stop_session"


def test_rejects_audio_chunk_that_is_not_pcm16(settings):
    with pytest.raises(ClientMessageError, match="偶数字节"):
        parse_client_message(
            json.dumps({"type": "audio", "data": encode(b"123")}),
            settings,
        )


def test_rejects_non_jpeg_video(settings):
    with pytest.raises(ClientMessageError, match="JPEG"):
        parse_client_message(
            json.dumps({
                "type": "video_frame",
                "timestamp": 1_000,
                "sequence": 1,
                "data": encode(b"not-jpeg"),
            }),
            settings,
            now_ms=1_100,
        )


def test_rejects_stale_video_frame(settings):
    jpeg = b"\xff\xd8payload\xff\xd9"
    with pytest.raises(ClientMessageError, match="过期"):
        parse_client_message(
            json.dumps({
                "type": "video_frame",
                "timestamp": 1_000,
                "sequence": 2,
                "data": encode(jpeg),
            }),
            settings,
            now_ms=3_001,
        )
```

Update the test fixture:

```python
@pytest.fixture
def settings():
    return Settings(
        gemini_api_key="test-key",
        max_audio_bytes=8_192,
        max_video_bytes=512 * 1024,
        max_text_chars=10,
        max_frame_age_ms=2_000,
    )
```

Add to `backend/tests/test_config.py`:

```python
def test_realtime_limits_have_cost_safe_defaults():
    settings = Settings(gemini_api_key="test-key")

    assert settings.max_audio_bytes == 8_192
    assert settings.max_video_bytes == 512 * 1024
    assert settings.max_frame_age_ms == 2_000
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
cd backend
uv run pytest tests/test_messages.py tests/test_config.py -v
```

Expected: FAIL because lifecycle message types, `timestamp`, `sequence`, `now_ms`, JPEG validation, and the new settings do not exist.

- [ ] **Step 3: Extend the protocol and configuration**

In `backend/app/core/config.py`, add:

```python
    max_audio_bytes: int = 8 * 1024
    max_video_bytes: int = 512 * 1024
    max_frame_age_ms: int = 2_000
```

Replace the message type and dataclass in `backend/app/api/messages.py` with:

```python
MessageType = Literal[
    "ping",
    "pong",
    "start_session",
    "stop_session",
    "audio",
    "video_frame",
    "text",
]


@dataclass(frozen=True, slots=True)
class ClientMessage:
    type: MessageType
    data: bytes | str | None = None
    timestamp_ms: int | None = None
    sequence: int | None = None
```

Change the parser signature and add lifecycle handling:

```python
def parse_client_message(
    raw_message: str,
    settings: Settings,
    *,
    now_ms: int | None = None,
) -> ClientMessage:
    try:
        payload = json.loads(raw_message)
    except json.JSONDecodeError as exc:
        raise ClientMessageError("消息不是有效的 JSON") from exc
    if not isinstance(payload, dict):
        raise ClientMessageError("消息必须是 JSON 对象")

    message_type = payload.get("type")
    if message_type in {"ping", "pong", "start_session", "stop_session"}:
        return ClientMessage(type=message_type)
```

Use this audio branch:

```python
    if message_type == "audio":
        data = _parse_base64(payload.get("data"), settings.max_audio_bytes)
        if len(data) % 2:
            raise ClientMessageError("PCM16 音频必须包含偶数字节")
        return ClientMessage(type="audio", data=data)
```

Use this video branch:

```python
    if message_type == "video_frame":
        data = _parse_base64(payload.get("data"), settings.max_video_bytes)
        if not (data.startswith(b"\xff\xd8") and data.endswith(b"\xff\xd9")):
            raise ClientMessageError("视频帧必须是完整的 JPEG 图片")

        timestamp_ms = payload.get("timestamp")
        sequence = payload.get("sequence")
        if not isinstance(timestamp_ms, int) or not isinstance(sequence, int):
            raise ClientMessageError("视频帧必须包含整数 timestamp 和 sequence")

        current_ms = now_ms if now_ms is not None else time.time_ns() // 1_000_000
        if current_ms - timestamp_ms > settings.max_frame_age_ms:
            raise ClientMessageError("视频帧已经过期")

        return ClientMessage(
            type="video_frame",
            data=data,
            timestamp_ms=timestamp_ms,
            sequence=sequence,
        )
```

Add `import time` to `backend/app/api/messages.py`.

Update `backend/.env.example`:

```env
MAX_AUDIO_BYTES=8192
MAX_VIDEO_BYTES=524288
MAX_FRAME_AGE_MS=2000
```

- [ ] **Step 4: Run the focused tests and verify they pass**

Run:

```bash
cd backend
uv run pytest tests/test_messages.py tests/test_config.py -v
```

Expected: PASS.

- [ ] **Step 5: Run the full backend suite**

Run:

```bash
cd backend
uv run pytest -v
```

Expected: all backend tests pass.

- [ ] **Step 6: Commit the protocol change**

```bash
git add backend/app/api/messages.py backend/app/core/config.py \
  backend/.env.example backend/tests/test_messages.py backend/tests/test_config.py
git commit -m "feat: add bounded realtime media protocol"
```

---

### Task 2: Prioritize Audio And Keep Only The Latest Video Frame

**Files:**
- Create: `backend/app/services/input_scheduler.py`
- Create: `backend/tests/test_input_scheduler.py`
- Modify: `backend/app/api/websocket.py`

- [ ] **Step 1: Write failing scheduler tests**

Create `backend/tests/test_input_scheduler.py`:

```python
import asyncio

from app.services.input_scheduler import InputScheduler


class FakeSession:
    def __init__(self):
        self.calls = []

    async def send_audio(self, data):
        self.calls.append(("audio", data))

    async def send_video_frame(self, data):
        self.calls.append(("video", data))

    async def send_text(self, data):
        self.calls.append(("text", data))


def test_latest_video_frame_replaces_older_pending_frame():
    async def scenario():
        scheduler = InputScheduler(audio_capacity=4)
        scheduler.submit_video(b"old", sequence=1)
        scheduler.submit_video(b"new", sequence=2)

        assert scheduler.take_latest_video() == (b"new", 2)
        assert scheduler.take_latest_video() is None

    asyncio.run(scenario())


def test_audio_is_sent_before_pending_video():
    async def scenario():
        scheduler = InputScheduler(audio_capacity=4)
        session = FakeSession()
        scheduler.submit_video(b"frame", sequence=1)
        await scheduler.submit_audio(b"audio")

        worker = asyncio.create_task(scheduler.run(session))
        await asyncio.sleep(0)
        await scheduler.close()
        await worker

        assert session.calls[:2] == [
            ("audio", b"audio"),
            ("video", b"frame"),
        ]

    asyncio.run(scenario())


def test_audio_queue_applies_backpressure():
    async def scenario():
        scheduler = InputScheduler(audio_capacity=1)
        await scheduler.submit_audio(b"first")
        second = asyncio.create_task(scheduler.submit_audio(b"second"))

        await asyncio.sleep(0)
        assert not second.done()

        assert await scheduler.take_audio() == b"first"
        await second

    asyncio.run(scenario())
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
cd backend
uv run pytest tests/test_input_scheduler.py -v
```

Expected: FAIL with `ModuleNotFoundError: app.services.input_scheduler`.

- [ ] **Step 3: Implement the bounded scheduler**

Create `backend/app/services/input_scheduler.py`:

```python
import asyncio
from dataclasses import dataclass

from app.services.gemini_service import GeminiSession


@dataclass(frozen=True, slots=True)
class PendingVideo:
    data: bytes
    sequence: int


class InputScheduler:
    def __init__(self, audio_capacity: int):
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
        if self._latest_video is None or sequence > self._latest_video.sequence:
            self._latest_video = PendingVideo(data, sequence)
            self._wake.set()

    async def take_audio(self) -> bytes:
        return await self._audio.get()

    def take_latest_video(self) -> tuple[bytes, int] | None:
        if self._latest_video is None:
            return None
        value = self._latest_video
        self._latest_video = None
        return value.data, value.sequence

    async def close(self) -> None:
        self._closed = True
        self._wake.set()

    async def run(self, session: GeminiSession) -> None:
        while True:
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

            self._wake.clear()
            await self._wake.wait()
```

- [ ] **Step 4: Route client media through the scheduler**

Change `_forward_client_messages` in `backend/app/api/websocket.py` to accept `scheduler: InputScheduler` instead of `session: GeminiSession`:

```python
async def _forward_client_messages(
    websocket: WebSocket,
    scheduler: InputScheduler,
) -> None:
    while True:
        raw_message = await websocket.receive_text()
        try:
            message = parse_client_message(raw_message, settings)
        except ClientMessageError as exc:
            logger.warning("收到无效客户端消息：%s", exc)
            await _send_error(websocket, str(exc))
            continue

        if message.type == "ping":
            await websocket.send_json({"type": "pong", "data": ""})
        elif message.type == "pong":
            continue
        elif message.type == "stop_session":
            return
        elif message.type == "audio":
            await scheduler.submit_audio(message.data)
        elif message.type == "video_frame":
            scheduler.submit_video(message.data, message.sequence)
        elif message.type == "text":
            await scheduler.submit_text(message.data)
```

In `_run_session`, construct the scheduler and add its worker:

```python
scheduler = InputScheduler(audio_capacity=settings.audio_queue_capacity)
tasks = {
    asyncio.create_task(
        _forward_client_messages(websocket, scheduler),
        name="接收客户端消息",
    ),
    asyncio.create_task(
        scheduler.run(session),
        name="发送模型输入",
    ),
    asyncio.create_task(
        _forward_gemini_responses(websocket, session),
        name="转发模型响应",
    ),
    asyncio.create_task(
        _keepalive(websocket),
        name="连接保活",
    ),
}
```

In the `finally` block, call `await scheduler.close()` before cancelling tasks.

Add to `Settings`:

```python
    audio_queue_capacity: int = 32
```

- [ ] **Step 5: Run scheduler and WebSocket tests**

Run:

```bash
cd backend
uv run pytest tests/test_input_scheduler.py tests/test_websocket.py -v
```

Expected: PASS.

- [ ] **Step 6: Run the full backend suite**

Run:

```bash
cd backend
uv run pytest -v
```

Expected: all backend tests pass.

- [ ] **Step 7: Commit the scheduler**

```bash
git add backend/app/services/input_scheduler.py \
  backend/app/api/websocket.py backend/app/core/config.py \
  backend/tests/test_input_scheduler.py backend/tests/test_websocket.py
git commit -m "feat: prioritize audio and replace stale video"
```

---

### Task 3: Start Cloud Sessions On Demand And Enforce Time Limits

**Files:**
- Create: `backend/app/services/session_runtime.py`
- Create: `backend/tests/test_session_runtime.py`
- Modify: `backend/app/api/websocket.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`
- Modify: `backend/tests/test_websocket.py`

- [ ] **Step 1: Write failing runtime timeout tests**

Create `backend/tests/test_session_runtime.py`:

```python
import asyncio

import pytest

from app.services.session_runtime import (
    SessionIdleTimeout,
    SessionLifetimeExceeded,
    SessionRuntime,
)


def test_idle_timeout_expires_without_input():
    async def scenario():
        runtime = SessionRuntime(idle_seconds=0.01, max_seconds=1)
        await runtime.start()
        with pytest.raises(SessionIdleTimeout):
            await runtime.wait_until_expired()

    asyncio.run(scenario())


def test_activity_refreshes_idle_deadline():
    async def scenario():
        runtime = SessionRuntime(idle_seconds=0.03, max_seconds=1)
        await runtime.start()
        await asyncio.sleep(0.02)
        runtime.record_activity()
        await asyncio.sleep(0.02)
        assert not runtime.expired

    asyncio.run(scenario())


def test_maximum_lifetime_is_not_extended_by_activity():
    async def scenario():
        runtime = SessionRuntime(idle_seconds=1, max_seconds=0.02)
        await runtime.start()
        runtime.record_activity()
        with pytest.raises(SessionLifetimeExceeded):
            await runtime.wait_until_expired()

    asyncio.run(scenario())
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
cd backend
uv run pytest tests/test_session_runtime.py -v
```

Expected: FAIL because `SessionRuntime` does not exist.

- [ ] **Step 3: Implement the runtime deadline model**

Create `backend/app/services/session_runtime.py`:

```python
import asyncio
import time


class SessionIdleTimeout(TimeoutError):
    pass


class SessionLifetimeExceeded(TimeoutError):
    pass


class SessionRuntime:
    def __init__(self, idle_seconds: float, max_seconds: float):
        self.idle_seconds = idle_seconds
        self.max_seconds = max_seconds
        self.started_at = 0.0
        self.last_activity_at = 0.0
        self.expired = False

    async def start(self) -> None:
        now = time.monotonic()
        self.started_at = now
        self.last_activity_at = now

    def record_activity(self) -> None:
        self.last_activity_at = time.monotonic()

    async def wait_until_expired(self) -> None:
        while True:
            now = time.monotonic()
            if now - self.started_at >= self.max_seconds:
                self.expired = True
                raise SessionLifetimeExceeded("实时会话已达到最长时限")
            if now - self.last_activity_at >= self.idle_seconds:
                self.expired = True
                raise SessionIdleTimeout("实时会话因长时间无输入而结束")
            await asyncio.sleep(min(self.idle_seconds / 4, 1))
```

- [ ] **Step 4: Add timeout settings**

Add to `backend/app/core/config.py`:

```python
    session_idle_seconds: float = 45.0
    session_max_seconds: float = 600.0
```

Add to `backend/.env.example`:

```env
SESSION_IDLE_SECONDS=45
SESSION_MAX_SECONDS=600
```

- [ ] **Step 5: Make `start_session` create Gemini and `stop_session` close it**

Refactor `websocket_endpoint` into an outer command loop:

```python
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    logger.info("客户端已连接")

    try:
        while True:
            raw_message = await websocket.receive_text()
            message = parse_client_message(raw_message, settings)
            if message.type == "ping":
                await websocket.send_json({"type": "pong", "data": ""})
                continue
            if message.type != "start_session":
                await _send_error(websocket, "请先发送 start_session")
                continue

            service = GeminiLiveService()
            async with service.connect() as session:
                await websocket.send_json({
                    "type": "status",
                    "data": "connected",
                })
                await _run_session(websocket, session)
                await websocket.send_json({
                    "type": "status",
                    "data": "stopped",
                })
    except WebSocketDisconnect:
        logger.info("客户端已断开连接")
```

Inside `_forward_client_messages`, return normally when receiving `stop_session`:

```python
if message.type == "stop_session":
    return
```

Construct a `SessionRuntime` in `_run_session`; call `runtime.record_activity()` after valid audio, video, or text input; add `runtime.wait_until_expired()` as another task.

Translate timeout exceptions into:

```json
{"type": "status", "data": "idle_timeout"}
```

or:

```json
{"type": "status", "data": "max_duration"}
```

- [ ] **Step 6: Add WebSocket lifecycle tests**

Add to `backend/tests/test_websocket.py`:

```python
def test_stop_session_finishes_client_forwarder():
    websocket = FakeWebSocket([
        json.dumps({"type": "stop_session", "data": ""}),
    ])
    scheduler = FakeScheduler()

    asyncio.run(_forward_client_messages(websocket, scheduler))

    assert scheduler.calls == []
```

Add this test for a new `_wait_for_start` helper:

```python
def test_wait_for_start_rejects_media_before_session():
    encoded = base64.b64encode(b"\x00\x00").decode("ascii")
    websocket = FakeWebSocket([
        json.dumps({"type": "audio", "data": encoded}),
        json.dumps({"type": "start_session", "data": ""}),
    ])

    asyncio.run(_wait_for_start(websocket))

    assert websocket.sent == [{
        "type": "error",
        "data": "请先发送 start_session",
    }]
```

Implement the helper in `backend/app/api/websocket.py` and call it before creating `GeminiLiveService`:

```python
async def _wait_for_start(websocket: WebSocket) -> None:
    while True:
        raw_message = await websocket.receive_text()
        message = parse_client_message(raw_message, settings)
        if message.type == "ping":
            await websocket.send_json({"type": "pong", "data": ""})
        elif message.type == "start_session":
            return
        else:
            await _send_error(websocket, "请先发送 start_session")
```

- [ ] **Step 7: Run focused and full tests**

Run:

```bash
cd backend
uv run pytest tests/test_session_runtime.py tests/test_websocket.py -v
uv run pytest -v
```

Expected: PASS.

- [ ] **Step 8: Commit lifecycle control**

```bash
git add backend/app/services/session_runtime.py backend/app/api/websocket.py \
  backend/app/core/config.py backend/.env.example \
  backend/tests/test_session_runtime.py backend/tests/test_websocket.py
git commit -m "feat: enforce realtime session lifecycle"
```

---

### Task 4: Enable Cost-Safe Media Resolution And Context Compression

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/services/gemini_service.py`
- Modify: `backend/tests/test_gemini_service.py`
- Modify: `backend/.env.example`

- [ ] **Step 1: Write a failing Live configuration test**

Add a pure config builder method to the desired API and test it first:

```python
def test_live_config_uses_low_media_resolution_and_context_compression():
    service = GeminiLiveService(Settings(gemini_api_key="test-key"))

    config = service.build_live_config()

    assert config.media_resolution == types.MediaResolution.MEDIA_RESOLUTION_LOW
    assert config.context_window_compression is not None
    assert config.context_window_compression.sliding_window is not None
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
cd backend
uv run pytest \
  tests/test_gemini_service.py::test_live_config_uses_low_media_resolution_and_context_compression \
  -v
```

Expected: FAIL because `build_live_config()` does not exist.

- [ ] **Step 3: Extract and update the Live configuration**

In `backend/app/services/gemini_service.py`, extract:

```python
def build_live_config(self) -> types.LiveConnectConfig:
    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        media_resolution=types.MediaResolution.MEDIA_RESOLUTION_LOW,
        context_window_compression=types.ContextWindowCompressionConfig(
            sliding_window=types.SlidingWindow(),
        ),
        system_instruction=SYSTEM_PROMPT,
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=self.settings.voice_name
                )
            )
        ),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                disabled=False,
                prefix_padding_ms=200,
                silence_duration_ms=800,
            )
        ),
    )
```

Replace the inline config in `connect()` with:

```python
config = self.build_live_config()
```

Do not add a high-resolution mode in this task. Low resolution remains the default cost-safe behavior; an OCR-specific mode requires a separate product decision and benchmark.

- [ ] **Step 4: Run tests**

Run:

```bash
cd backend
uv run pytest tests/test_gemini_service.py -v
uv run pytest -v
```

Expected: PASS.

- [ ] **Step 5: Commit Live cost defaults**

```bash
git add backend/app/services/gemini_service.py \
  backend/tests/test_gemini_service.py
git commit -m "feat: add cost-safe Gemini Live configuration"
```

---

### Task 5: Track Usage, Latency, And Per-Session Budget

**Files:**
- Create: `backend/app/services/usage.py`
- Create: `backend/tests/test_usage.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/services/gemini_service.py`
- Modify: `backend/app/services/session_runtime.py`
- Modify: `backend/app/api/websocket.py`
- Modify: `backend/.env.example`

- [ ] **Step 1: Write failing usage aggregation tests**

Create `backend/tests/test_usage.py`:

```python
from app.services.usage import SessionUsage


def test_usage_accumulates_media_and_token_totals():
    usage = SessionUsage()

    usage.record_audio(1_280)
    usage.record_video(40_000)
    usage.record_tokens(total=500, prompt=300, response=200)

    assert usage.audio_bytes == 1_280
    assert usage.video_bytes == 40_000
    assert usage.video_frames == 1
    assert usage.total_tokens == 500
    assert usage.prompt_tokens == 300
    assert usage.response_tokens == 200


def test_usage_reports_budget_exhaustion():
    usage = SessionUsage(token_budget=1_000)
    usage.record_tokens(total=1_001, prompt=700, response=301)

    assert usage.token_budget_exhausted
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
cd backend
uv run pytest tests/test_usage.py -v
```

Expected: FAIL because `SessionUsage` does not exist.

- [ ] **Step 3: Implement usage aggregation**

Create `backend/app/services/usage.py`:

```python
from dataclasses import dataclass
import time


@dataclass(slots=True)
class SessionUsage:
    token_budget: int = 50_000
    audio_bytes: int = 0
    video_bytes: int = 0
    video_frames: int = 0
    prompt_tokens: int = 0
    response_tokens: int = 0
    total_tokens: int = 0
    started_at: float = 0.0
    first_response_at: float | None = None

    def __post_init__(self) -> None:
        self.started_at = time.monotonic()

    def record_audio(self, byte_count: int) -> None:
        self.audio_bytes += byte_count

    def record_video(self, byte_count: int) -> None:
        self.video_bytes += byte_count
        self.video_frames += 1

    def record_tokens(self, *, total: int, prompt: int, response: int) -> None:
        self.total_tokens = max(self.total_tokens, total)
        self.prompt_tokens = max(self.prompt_tokens, prompt)
        self.response_tokens = max(self.response_tokens, response)

    def record_first_response(self) -> None:
        if self.first_response_at is None:
            self.first_response_at = time.monotonic()

    @property
    def token_budget_exhausted(self) -> bool:
        return self.total_tokens > self.token_budget
```

- [ ] **Step 4: Emit usage events from Gemini**

In `GeminiSession.receive()`, before `server_content` handling:

```python
usage_metadata = getattr(response, "usage_metadata", None)
if usage_metadata:
    yield {
        "type": "usage",
        "data": {
            "total_tokens": usage_metadata.total_token_count or 0,
            "prompt_tokens": usage_metadata.prompt_token_count or 0,
            "response_tokens": usage_metadata.response_token_count or 0,
        },
    }
```

Change the iterator type to:

```python
AsyncIterator[dict[str, str | dict[str, int]]]
```

- [ ] **Step 5: Enforce the token budget**

Add to `Settings` and `.env.example`:

```python
    session_token_budget: int = 50_000
```

```env
SESSION_TOKEN_BUDGET=50000
```

In `_forward_gemini_responses`, consume usage internally and send a compact session event to the client:

```python
if response["type"] == "usage":
    data = response["data"]
    usage.record_tokens(
        total=data["total_tokens"],
        prompt=data["prompt_tokens"],
        response=data["response_tokens"],
    )
    if usage.token_budget_exhausted:
        await websocket.send_json({
            "type": "status",
            "data": "token_budget_exhausted",
        })
        raise SessionTokenBudgetExceeded
    continue
```

Record audio and video byte counts when accepted by the scheduler. Log one Chinese summary at session end:

```python
logger.info(
    "会话统计：时长 %.1f 秒，音频 %d 字节，视频 %d 帧/%d 字节，总令牌 %d",
    time.monotonic() - usage.started_at,
    usage.audio_bytes,
    usage.video_frames,
    usage.video_bytes,
    usage.total_tokens,
)
```

- [ ] **Step 6: Add usage-event and latency tests**

Add to `backend/tests/test_gemini_service.py`:

```python
def test_receive_emits_usage_metadata():
    async def responses():
        yield SimpleNamespace(
            usage_metadata=SimpleNamespace(
                total_token_count=500,
                prompt_token_count=300,
                response_token_count=200,
            ),
            server_content=None,
            go_away=None,
            session_resumption_update=None,
        )

    session = GeminiSession(SimpleNamespace(receive=responses))

    async def collect():
        return [event async for event in session.receive()]

    assert asyncio.run(collect()) == [{
        "type": "usage",
        "data": {
            "total_tokens": 500,
            "prompt_tokens": 300,
            "response_tokens": 200,
        },
    }]
```

Add to `backend/tests/test_usage.py`:

```python
def test_first_response_latency_is_recorded_once(monkeypatch):
    times = iter([10.0, 10.25, 11.0])
    monkeypatch.setattr("app.services.usage.time.monotonic", lambda: next(times))
    usage = SessionUsage()

    usage.record_first_response()
    first_value = usage.first_response_at
    usage.record_first_response()

    assert first_value == 10.25
    assert usage.first_response_at == 10.25


def test_media_counts_only_change_when_recorded():
    usage = SessionUsage()

    assert usage.audio_bytes == 0
    assert usage.video_frames == 0
    usage.record_audio(1_280)
    usage.record_video(40_000)

    assert usage.audio_bytes == 1_280
    assert usage.video_frames == 1
    assert usage.video_bytes == 40_000
```

Use the existing `test_usage_reports_budget_exhaustion` as the direct budget-enforcement unit test. Add this helper and WebSocket test:

```python
class SessionTokenBudgetExceeded(RuntimeError):
    pass


def _record_usage_event(
    usage: SessionUsage,
    data: dict[str, int],
) -> None:
    usage.record_tokens(
        total=data["total_tokens"],
        prompt=data["prompt_tokens"],
        response=data["response_tokens"],
    )
    if usage.token_budget_exhausted:
        raise SessionTokenBudgetExceeded
```

```python
def test_usage_event_over_budget_raises():
    usage = SessionUsage(token_budget=100)

    with pytest.raises(SessionTokenBudgetExceeded):
        _record_usage_event(
            usage,
            {
                "total_tokens": 101,
                "prompt_tokens": 60,
                "response_tokens": 41,
            },
        )
```

Call `_record_usage_event()` from `_forward_gemini_responses` when the event type is `usage`; catch `SessionTokenBudgetExceeded` in the session coordinator, send `token_budget_exhausted`, and close the Gemini context.

- [ ] **Step 7: Run tests**

Run:

```bash
cd backend
uv run pytest tests/test_usage.py tests/test_gemini_service.py \
  tests/test_websocket.py -v
uv run pytest -v
```

Expected: PASS.

- [ ] **Step 8: Commit observability and budget enforcement**

```bash
git add backend/app/services/usage.py backend/app/services/gemini_service.py \
  backend/app/services/session_runtime.py backend/app/api/websocket.py \
  backend/app/core/config.py backend/.env.example \
  backend/tests/test_usage.py backend/tests/test_gemini_service.py \
  backend/tests/test_websocket.py
git commit -m "feat: enforce Gemini session usage budget"
```

---

### Task 6: Handle User Interruption Immediately

**Files:**
- Modify: `backend/app/services/gemini_service.py`
- Modify: `backend/tests/test_gemini_service.py`
- Modify: `frontend/hooks/useAudioPlayer.ts`
- Modify: `frontend/app/page.tsx`
- Create: `frontend/lib/audioQueue.ts`
- Create: `frontend/lib/audioQueue.test.ts`
- Modify: `frontend/package.json`
- Create: `frontend/vitest.config.ts`

- [ ] **Step 1: Add frontend test tooling**

Update `frontend/package.json`:

```json
{
  "scripts": {
    "test": "vitest run"
  },
  "devDependencies": {
    "vitest": "^3.2.4"
  }
}
```

Create `frontend/vitest.config.ts`:

```typescript
import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    environment: 'node',
  },
})
```

Run:

```bash
cd frontend
npm install
```

- [ ] **Step 2: Write failing backend interruption test**

Add to `backend/tests/test_gemini_service.py` using `SimpleNamespace`:

```python
def test_receive_emits_interrupted_event():
    async def responses():
        yield SimpleNamespace(
            usage_metadata=None,
            server_content=SimpleNamespace(
                interrupted=True,
                output_transcription=None,
                model_turn=None,
                turn_complete=False,
            ),
            go_away=None,
            session_resumption_update=None,
        )

    fake_session = SimpleNamespace(receive=responses)
    session = GeminiSession(fake_session)

    async def collect():
        return [event async for event in session.receive()]

    assert asyncio.run(collect()) == [{
        "type": "interrupted",
        "data": "",
    }]
```

- [ ] **Step 3: Run the backend test and verify it fails**

Run:

```bash
cd backend
uv run pytest \
  tests/test_gemini_service.py::test_receive_emits_interrupted_event -v
```

Expected: FAIL because interruption is ignored.

- [ ] **Step 4: Emit interruption from the backend**

In `GeminiSession.receive()`:

```python
if getattr(server_content, "interrupted", False):
    yield {"type": "interrupted", "data": ""}
```

Run the focused backend test and expect PASS.

- [ ] **Step 5: Write a failing pure playback-queue test**

Create `frontend/lib/audioQueue.test.ts`:

```typescript
import { describe, expect, it } from 'vitest'
import { AudioQueue } from './audioQueue'

describe('AudioQueue', () => {
  it('clears pending buffers and stops the active source', () => {
    let stopped = 0
    const queue = new AudioQueue<AudioBuffer>()
    queue.enqueue({} as AudioBuffer)
    queue.setActiveSource({ stop: () => { stopped += 1 } } as AudioBufferSourceNode)

    queue.interrupt()

    expect(queue.size).toBe(0)
    expect(stopped).toBe(1)
  })
})
```

- [ ] **Step 6: Run the frontend test and verify it fails**

Run:

```bash
cd frontend
npm test -- audioQueue.test.ts
```

Expected: FAIL because `AudioQueue` does not exist.

- [ ] **Step 7: Implement interruptible playback**

Create `frontend/lib/audioQueue.ts`:

```typescript
export class AudioQueue<T> {
  private items: T[] = []
  private activeSource: AudioBufferSourceNode | null = null

  enqueue(item: T) {
    this.items.push(item)
  }

  shift() {
    return this.items.shift()
  }

  setActiveSource(source: AudioBufferSourceNode | null) {
    this.activeSource = source
  }

  interrupt() {
    this.items = []
    try {
      this.activeSource?.stop()
    } catch {}
    this.activeSource = null
  }

  get size() {
    return this.items.length
  }
}
```

Refactor `useAudioPlayer.ts` to use `AudioQueue<AudioBuffer>`, store each active source, and return:

```typescript
const interrupt = useCallback(() => {
  audioQueue.current.interrupt()
  playing.current = false
  isSpeakingRef.current = false
  setIsSpeaking(false)
}, [])

return { playAudio, interrupt, isSpeaking, isSpeakingRef }
```

In `page.tsx`:

```typescript
const { playAudio, interrupt, isSpeaking, isSpeakingRef } = useAudioPlayer()
```

Handle the server event:

```typescript
if (last.type === 'interrupted') {
  interrupt()
  setIsProcessing(false)
}
```

- [ ] **Step 8: Run backend and frontend verification**

Run:

```bash
cd backend
uv run pytest tests/test_gemini_service.py -v

cd ../frontend
npm test
npm run lint
npm run build
```

Expected: all commands succeed.

- [ ] **Step 9: Commit interruption support**

```bash
git add backend/app/services/gemini_service.py \
  backend/tests/test_gemini_service.py \
  frontend/lib/audioQueue.ts frontend/lib/audioQueue.test.ts \
  frontend/hooks/useAudioPlayer.ts frontend/app/page.tsx \
  frontend/package.json frontend/package-lock.json frontend/vitest.config.ts
git commit -m "feat: stop model playback on interruption"
```

---

### Task 7: Produce Low-Latency Audio Chunks On The Client

**Files:**
- Create: `frontend/lib/audio.ts`
- Create: `frontend/lib/audio.test.ts`
- Modify: `frontend/app/page.tsx`
- Modify: `backend/app/api/messages.py`
- Modify: `backend/tests/test_messages.py`

- [ ] **Step 1: Write failing audio chunk tests**

Create `frontend/lib/audio.test.ts`:

```typescript
import { describe, expect, it } from 'vitest'
import { PcmChunker } from './audio'

describe('PcmChunker', () => {
  it('emits 40 ms chunks at 16 kHz', () => {
    const chunker = new PcmChunker(640)
    const samples = new Float32Array(1280).fill(0.5)

    const chunks = chunker.push(samples)

    expect(chunks).toHaveLength(2)
    expect(chunks[0].byteLength).toBe(1280)
  })

  it('retains an incomplete tail for the next callback', () => {
    const chunker = new PcmChunker(640)

    expect(chunker.push(new Float32Array(320))).toHaveLength(0)
    expect(chunker.push(new Float32Array(320))).toHaveLength(1)
  })
})
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
cd frontend
npm test -- audio.test.ts
```

Expected: FAIL because `PcmChunker` does not exist.

- [ ] **Step 3: Implement a 40 ms PCM chunker**

Create `frontend/lib/audio.ts`:

```typescript
export class PcmChunker {
  private pending = new Float32Array(0)

  constructor(private readonly samplesPerChunk = 640) {}

  push(input: Float32Array): Uint8Array[] {
    const combined = new Float32Array(this.pending.length + input.length)
    combined.set(this.pending)
    combined.set(input, this.pending.length)

    const output: Uint8Array[] = []
    let offset = 0
    while (combined.length - offset >= this.samplesPerChunk) {
      const pcm = new Int16Array(this.samplesPerChunk)
      for (let index = 0; index < pcm.length; index += 1) {
        const sample = Math.max(-1, Math.min(1, combined[offset + index]))
        pcm[index] = sample < 0 ? sample * 0x8000 : sample * 0x7fff
      }
      output.push(new Uint8Array(pcm.buffer))
      offset += this.samplesPerChunk
    }
    this.pending = combined.slice(offset)
    return output
  }
}

export function bytesToBase64(bytes: Uint8Array): string {
  let binary = ''
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary)
}
```

- [ ] **Step 4: Use the chunker in `page.tsx`**

Create one `PcmChunker(640)` per active session. Replace direct conversion of the whole `onaudioprocess` input with:

```typescript
for (const chunk of chunker.push(input)) {
  sendAudio(bytesToBase64(chunk))
}
```

Use `createScriptProcessor(1024, 1, 1)` only as a browser callback source; the chunker determines the network packet size.

- [ ] **Step 5: Add backend lower-bound validation**

Add this test to `backend/tests/test_messages.py`:

```python
def test_accepts_40ms_pcm_chunk(settings):
    pcm = b"\x00\x00" * 640
    message = parse_client_message(
        json.dumps({"type": "audio", "data": encode(pcm)}),
        settings,
    )
    assert message.data == pcm
```

Keep the backend maximum at 8 KB so short scheduling jitter is tolerated without accepting large buffered audio.

- [ ] **Step 6: Run verification**

Run:

```bash
cd frontend
npm test
npm run lint
npm run build

cd ../backend
uv run pytest tests/test_messages.py -v
uv run pytest -v
```

Expected: PASS.

- [ ] **Step 7: Commit low-latency audio**

```bash
git add frontend/lib/audio.ts frontend/lib/audio.test.ts \
  frontend/app/page.tsx backend/tests/test_messages.py
git commit -m "feat: stream low-latency microphone chunks"
```

---

### Task 8: Add Adaptive And Fresh Video Sampling

**Files:**
- Create: `frontend/lib/framePolicy.ts`
- Create: `frontend/lib/framePolicy.test.ts`
- Modify: `frontend/hooks/useCamera.ts`
- Modify: `frontend/hooks/useWebSocket.ts`
- Modify: `frontend/app/page.tsx`

- [ ] **Step 1: Write failing frame policy tests**

Create `frontend/lib/framePolicy.test.ts`:

```typescript
import { describe, expect, it } from 'vitest'
import { FramePolicy } from './framePolicy'

describe('FramePolicy', () => {
  it('sends the first frame', () => {
    const policy = new FramePolicy()
    expect(policy.shouldSend(new Uint8ClampedArray([0, 0, 0]), 0, false)).toBe(true)
  })

  it('suppresses an unchanged frame before the idle interval', () => {
    const policy = new FramePolicy()
    const pixels = new Uint8ClampedArray([10, 10, 10])
    expect(policy.shouldSend(pixels, 0, false)).toBe(true)
    expect(policy.shouldSend(pixels, 1_000, false)).toBe(false)
  })

  it('sends changed frames and raises frequency while the user speaks', () => {
    const policy = new FramePolicy()
    policy.shouldSend(new Uint8ClampedArray([0, 0, 0]), 0, false)

    expect(
      policy.shouldSend(new Uint8ClampedArray([255, 255, 255]), 1_000, true),
    ).toBe(true)
  })
})
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
cd frontend
npm test -- framePolicy.test.ts
```

Expected: FAIL because `FramePolicy` does not exist.

- [ ] **Step 3: Implement the pure policy**

Create `frontend/lib/framePolicy.ts`:

```typescript
export class FramePolicy {
  private previous: Uint8ClampedArray | null = null
  private lastSentAt = -Infinity

  constructor(
    private readonly changedIntervalMs = 1_000,
    private readonly idleIntervalMs = 5_000,
    private readonly differenceThreshold = 12,
  ) {}

  shouldSend(
    pixels: Uint8ClampedArray,
    nowMs: number,
    userSpeaking: boolean,
  ): boolean {
    const difference = this.previous
      ? meanAbsoluteDifference(this.previous, pixels)
      : Infinity
    const changed = difference >= this.differenceThreshold
    const minimumInterval = userSpeaking
      ? this.changedIntervalMs
      : changed
        ? this.changedIntervalMs
        : this.idleIntervalMs

    this.previous = pixels.slice()
    if (nowMs - this.lastSentAt < minimumInterval) return false
    this.lastSentAt = nowMs
    return changed || nowMs - this.lastSentAt >= this.idleIntervalMs
  }
}

function meanAbsoluteDifference(
  left: Uint8ClampedArray,
  right: Uint8ClampedArray,
): number {
  const length = Math.min(left.length, right.length)
  let total = 0
  for (let index = 0; index < length; index += 1) {
    total += Math.abs(left[index] - right[index])
  }
  return length === 0 ? 0 : total / length
}
```

Before implementation, correct the final return to compare against the previous `lastSentAt` value:

```typescript
const elapsed = nowMs - this.lastSentAt
if (elapsed < minimumInterval) return false
this.lastSentAt = nowMs
return changed || elapsed >= this.idleIntervalMs
```

- [ ] **Step 4: Return a thumbnail fingerprint and JPEG from camera capture**

Change `captureFrame()` in `frontend/hooks/useCamera.ts` to return:

```typescript
type CapturedFrame = {
  jpegBase64: string
  fingerprint: Uint8ClampedArray
}
```

Use a 32×24 secondary canvas for the fingerprint:

```typescript
const sampleCanvas = document.createElement('canvas')
sampleCanvas.width = 32
sampleCanvas.height = 24
const sampleContext = sampleCanvas.getContext('2d', { willReadFrequently: true })
sampleContext?.drawImage(video, 0, 0, 32, 24)
const fingerprint = sampleContext
  ? sampleContext.getImageData(0, 0, 32, 24).data
  : new Uint8ClampedArray()
```

Keep the uploaded JPEG at 640×480, quality `0.6`.

- [ ] **Step 5: Add timestamp and sequence to the WebSocket protocol**

Change `sendFrame` in `frontend/hooks/useWebSocket.ts`:

```typescript
const sendFrame = useCallback((
  base64: string,
  timestamp: number,
  sequence: number,
) => {
  sendMessage({
    type: 'video_frame',
    data: base64,
    timestamp,
    sequence,
  })
}, [sendMessage])
```

Replace the fixed 1.5-second interval in `page.tsx` with a 500 ms policy check. Only call `sendFrame()` when `FramePolicy.shouldSend()` returns true. Increment `sequenceRef.current` for every sent frame.

- [ ] **Step 6: Run frontend verification**

Run:

```bash
cd frontend
npm test
npm run lint
npm run build
```

Expected: PASS.

- [ ] **Step 7: Run the backend protocol suite**

Run:

```bash
cd backend
uv run pytest tests/test_messages.py tests/test_websocket.py -v
uv run pytest -v
```

Expected: PASS.

- [ ] **Step 8: Commit adaptive vision**

```bash
git add frontend/lib/framePolicy.ts frontend/lib/framePolicy.test.ts \
  frontend/hooks/useCamera.ts frontend/hooks/useWebSocket.ts \
  frontend/app/page.tsx
git commit -m "feat: adapt video uploads to scene changes"
```

---

### Task 9: Add Session Resumption And Graceful GoAway Handling

**Files:**
- Modify: `backend/app/services/gemini_service.py`
- Modify: `backend/tests/test_gemini_service.py`
- Modify: `backend/app/api/websocket.py`
- Modify: `backend/tests/test_websocket.py`

- [ ] **Step 1: Write failing server-event tests**

Add to `backend/tests/test_gemini_service.py`:

```python
def test_receive_emits_resumption_handle_and_go_away():
    async def responses():
        yield SimpleNamespace(
            usage_metadata=None,
            server_content=None,
            session_resumption_update=SimpleNamespace(
                resumable=True,
                new_handle="resume-123",
            ),
            go_away=None,
        )
        yield SimpleNamespace(
            usage_metadata=None,
            server_content=None,
            session_resumption_update=None,
            go_away=SimpleNamespace(time_left="5s"),
        )

    fake_session = SimpleNamespace(receive=responses)
    session = GeminiSession(fake_session)

    async def collect():
        return [event async for event in session.receive()]

    assert asyncio.run(collect()) == [
        {"type": "session_resumption", "data": "resume-123"},
        {"type": "go_away", "data": "5s"},
    ]
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
cd backend
uv run pytest \
  tests/test_gemini_service.py::test_receive_emits_resumption_handle_and_go_away \
  -v
```

Expected: FAIL because these server messages are ignored.

- [ ] **Step 3: Enable session resumption in the Live config**

Add to `build_live_config()`:

```python
session_resumption=types.SessionResumptionConfig(transparent=True),
```

In `GeminiSession.receive()`:

```python
resumption = getattr(response, "session_resumption_update", None)
if resumption and resumption.new_handle:
    yield {
        "type": "session_resumption",
        "data": resumption.new_handle,
    }

go_away = getattr(response, "go_away", None)
if go_away:
    yield {
        "type": "go_away",
        "data": str(go_away.time_left or ""),
    }
```

- [ ] **Step 4: Preserve the latest handle in the WebSocket runtime**

Define the result returned by one connected Gemini session:

```python
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class SessionExit:
    reason: Literal["closed", "go_away"]
    resumption_handle: str | None = None
```

Change `_run_session()` to return `SessionExit`. `_forward_gemini_responses` receives a mutable state object containing the latest handle. When it sees `session_resumption`, update that state and do not forward the token to the browser. When it sees `go_away`, raise:

```python
class GeminiReconnectRequired(RuntimeError):
    pass
```

Catch that exception inside `_run_session()` and return:

```python
return SessionExit(
    reason="go_away",
    resumption_handle=state.resumption_handle,
)
```

When a normal worker finishes, return:

```python
return SessionExit(
    reason="closed",
    resumption_handle=state.resumption_handle,
)
```

Extend `GeminiLiveService.connect()` to accept:

```python
async def connect(
    self,
    resumption_handle: str | None = None,
) -> AsyncIterator["GeminiSession"]:
```

Build:

```python
session_resumption=types.SessionResumptionConfig(
    handle=resumption_handle,
    transparent=True,
)
```

Add this connection loop:

```python
async def _run_gemini_with_resumption(
    websocket: WebSocket,
    service: GeminiLiveService,
    runtime: SessionRuntime,
    usage: SessionUsage,
) -> None:
    resumption_handle: str | None = None

    while not runtime.expired:
        async with service.connect(resumption_handle) as session:
            result = await _run_session(
                websocket,
                session,
                runtime,
                usage,
            )

        if result.reason != "go_away":
            return
        if not result.resumption_handle:
            raise RuntimeError("Gemini 请求重连但没有提供恢复令牌")

        resumption_handle = result.resumption_handle
        await websocket.send_json({
            "type": "status",
            "data": "reconnecting",
        })
```

Each `_run_session()` invocation creates a new scheduler bound to the new Gemini session. The outer browser WebSocket remains open; media arriving during the short reconnect stays in the browser WebSocket buffer and is consumed by the next `_run_session()` invocation.

- [ ] **Step 5: Add reconnect tests**

Add this fake service and test to `backend/tests/test_websocket.py`:

```python
class FakeSessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeResumableService:
    def __init__(self):
        self.handles = []
        self.sessions = iter([
            object(),
            object(),
        ])

    def connect(self, resumption_handle=None):
        self.handles.append(resumption_handle)
        return FakeSessionContext(next(self.sessions))


def test_reconnects_with_latest_resumption_handle():
    websocket = FakeWebSocket([])
    service = FakeResumableService()
    runtime = SimpleNamespace(expired=False)
    usage = SessionUsage()
    results = iter([
        SessionExit("go_away", "resume-123"),
        SessionExit("closed", "resume-123"),
    ])

    async def fake_run_session(websocket, session, runtime, usage):
        return next(results)

    asyncio.run(
        _run_gemini_with_resumption(
            websocket,
            service,
            runtime,
            usage,
            run_session=fake_run_session,
        )
    )

    assert service.handles == [None, "resume-123"]
    assert {"type": "status", "data": "reconnecting"} in websocket.sent
```

Allow test injection without changing production calls:

```python
async def _run_gemini_with_resumption(
    websocket: WebSocket,
    service: GeminiLiveService,
    runtime: SessionRuntime,
    usage: SessionUsage,
    run_session=_run_session,
) -> None:
```

- [ ] **Step 6: Run full backend verification**

Run:

```bash
cd backend
uv run pytest -v
uv run python -m compileall -q app tests
```

Expected: PASS.

- [ ] **Step 7: Commit session continuity**

```bash
git add backend/app/services/gemini_service.py \
  backend/app/api/websocket.py backend/tests/test_gemini_service.py \
  backend/tests/test_websocket.py
git commit -m "feat: resume Gemini Live sessions after GoAway"
```

---

### Task 10: Document And Verify Operational Defaults

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document operational defaults**

Add a “实时质量与成本控制” section to `README.md` documenting:

```text
- 音频块：40 ms
- 视频：变化时最高约 1 FPS，静止时约 0.2 FPS
- 后端视频队列：仅保留最新帧
- 空闲超时：45 秒
- 最长会话：600 秒
- 默认媒体分辨率：LOW
- 上下文压缩：启用
- 单会话 token 预算：50000
```

Document these emitted status events:

```text
idle_timeout
max_duration
token_budget_exhausted
reconnecting
```

- [ ] **Step 2: Run all verification commands**

Run:

```bash
cd backend
uv sync --locked
uv run pytest -v
uv run python -m compileall -q app tests

cd ../frontend
npm ci
npm test
npm run lint
npm run build
```

Expected:

- all backend tests pass;
- Python compilation exits with code 0;
- all frontend tests pass;
- ESLint exits with code 0;
- Next.js production build exits with code 0.

- [ ] **Step 3: Check for unsafe secrets and obsolete behavior**

Run:

```bash
rg -n 'GEMINI_API_KEY=.+|AQ\\.' . \
  -g '!backend/.env' -g '!frontend/node_modules/**' -g '!.git/**'
rg -n '\\bprint\\s*\\(' backend/app
```

Expected: no real API key and no backend `print()` calls.

- [ ] **Step 4: Commit final documentation**

```bash
git add README.md
git commit -m "docs: document realtime quality and cost controls"
```

---

## PR Order

Implement each task as one PR in this order:

1. Bounded realtime media protocol
2. Audio-priority/latest-video scheduler
3. Explicit session lifecycle and time limits
4. Cost-safe Live configuration
5. Usage metrics and token budget
6. User interruption
7. Low-latency client audio chunks
8. Adaptive video uploads
9. Session resumption
10. Acceptance test and documentation

Every PR must run the full backend suite. PRs that modify the frontend must also run `npm test`, `npm run lint`, and `npm run build`.
