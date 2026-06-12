# Frontend Integration Contract

This document is the boundary between this backend repository and the
separately developed frontend project.

## Ownership

The backend owns protocol validation, Gemini Live connectivity, scheduling,
lifecycle limits, usage limits, and server events.

The frontend owns camera and microphone capture, PCM generation, JPEG
sampling, playback, UI state, reconnection UX, and browser tests.

The frontend must not depend on backend Python modules. It should depend only
on the released protocol in this document.

## Protocol Status

This contract distinguishes released behavior from planned behavior:

- **Released** means the behavior exists on the current `main` branch.
- **Planned** means the frontend may prepare support, but must not require the
  behavior until the named backend PR has merged.
- Every backend PR that changes the protocol must update this document in the
  same PR.

## Endpoint

Development endpoint:

```text
ws://localhost:8000/ws
```

All messages are UTF-8 JSON objects. Binary media is Base64-encoded in the
`data` field.

---

## Released Protocol

### Connection Lifecycle

The current backend creates Gemini Live immediately after accepting the
browser WebSocket:

1. Frontend opens the WebSocket.
2. Backend creates Gemini Live.
3. Backend sends `status: connected`.
4. Frontend sends text, audio, and video messages.
5. When either side ends the live session, the backend closes the browser
   WebSocket.

There is currently no `start_session` or `stop_session` message.

### Client Ping

```json
{"type":"ping","data":""}
```

The backend replies:

```json
{"type":"pong","data":""}
```

### Client Pong

```json
{"type":"pong","data":""}
```

The backend accepts it silently.

### Client Text

```json
{"type":"text","data":"请描述镜头中的内容"}
```

Requirements:

- `data` is a non-empty string.
- Maximum length is 2,000 characters by default.

### Client Audio

```json
{"type":"audio","data":"<base64-pcm16>"}
```

Requirements:

- PCM signed 16-bit little-endian, mono, 16 kHz.
- Maximum decoded size is 262,144 bytes by default.
- The current parser validates Base64 and size, but does not yet validate an
  even PCM16 byte count.

Recommended frontend chunk duration is 20–40 ms even though the current
backend accepts larger payloads.

### Client Video Frame

```json
{"type":"video_frame","data":"<base64-jpeg>"}
```

Requirements:

- Send a complete JPEG image because the backend forwards it to Gemini as
  `image/jpeg`.
- Maximum decoded size is 2,097,152 bytes by default.
- The current parser validates Base64 and size, but does not yet validate JPEG
  markers, timestamps, or sequence numbers.

### Server Connected Status

```json
{"type":"status","data":"connected"}
```

The frontend may begin sending media after this event.

### Server Error

```json
{"type":"error","data":"媒体内容不是有效的 Base64 数据"}
```

Errors are Chinese user-facing strings. A protocol error does not necessarily
close the WebSocket.

### Server Keepalive Ping

```json
{"type":"ping","data":""}
```

The frontend should reply with `pong`.

### Server Text

```json
{"type":"text","data":"模型转写文本"}
```

Append `data` to the model transcript.

### Server Audio

```json
{"type":"audio","data":"<base64-pcm16-24khz>"}
```

`data` is Base64-encoded model audio. Decode and play it as signed 16-bit
little-endian, mono PCM at 24 kHz.

### Server Turn Complete

```json
{"type":"turn_complete","data":""}
```

The current model response turn has finished. The frontend may use this event
to finalize transcript or playback UI state.

---

## Planned Protocol Evolution

### Task 1: Bounded Media Protocol

Activated only after the Task 1 PR merges.

Changes:

- Audio maximum becomes 8,192 decoded bytes by default.
- PCM16 audio must have an even decoded byte count.
- Video maximum becomes 524,288 decoded bytes by default.
- Video must contain JPEG start and end markers.
- Video messages require Unix epoch `timestamp` in milliseconds and an
  increasing integer `sequence`.
- Timestamp skew is limited to 2,000 ms in either direction by default.

Target video message:

```json
{
  "type":"video_frame",
  "data":"<base64-jpeg>",
  "timestamp":1781234567890,
  "sequence":42
}
```

### Task 2: Bounded Scheduler

Activated only after the Task 2 PR merges.

Changes:

- Text and audio submissions are bounded.
- The backend may return a Chinese backpressure error when a submission is
  already pending.
- Only the newest pending video frame is retained.
- The frontend should still perform visual-change detection and adaptive
  sampling before upload.

### Task 3: Explicit Session Lifecycle

Activated only after the Task 3 PR merges.

The browser WebSocket and Gemini cloud session become separate:

1. Frontend opens the WebSocket.
2. Frontend sends `start_session` after explicit user action.
3. Backend creates Gemini Live and sends `status: connected`.
4. Frontend sends media.
5. Frontend sends `stop_session`.
6. Backend sends `status: stopped`.
7. The same browser WebSocket may start another cloud session.

Target start message:

```json
{"type":"start_session","data":""}
```

Target stop message:

```json
{"type":"stop_session","data":""}
```

Target terminal statuses:

| Value | Meaning | Frontend action |
|---|---|---|
| `stopped` | User stop or model stream ended | Stop media; allow restart |
| `idle_timeout` | No accepted input for 45 seconds by default | Stop media; allow restart |
| `max_duration` | Session reached 600 seconds by default | Stop media; allow restart |

After Task 3 merges, keep the browser WebSocket open after a terminal status.

### Task 5: Usage And Budget

Activated only after the Task 5 PR merges.

Target budget status:

```json
{"type":"status","data":"budget_exceeded"}
```

Target usage event:

```json
{
  "type":"usage",
  "data":{
    "audio_bytes":32000,
    "text_chars":120,
    "video_frames":8,
    "video_replaced_frames":3,
    "video_bytes":180000,
    "input_tokens":1200,
    "output_tokens":340,
    "total_tokens":1540,
    "duration_ms":25000,
    "first_response_latency_ms":480
  }
}
```

Field meanings:

- `audio_bytes`: accepted client audio bytes.
- `text_chars`: accepted client text characters.
- `video_frames`: accepted client video frames.
- `video_replaced_frames`: pending frames replaced before cloud forwarding.
- `video_bytes`: accepted client video bytes.
- `input_tokens`, `output_tokens`, `total_tokens`: Gemini usage metadata.
- `duration_ms`: cloud-session duration.
- `first_response_latency_ms`: delay from the first accepted input to the
  first model output.

The backend is the source of truth for limit enforcement.

### Task 6: Interruption

Activated only after the Task 6 PR merges.

```json
{"type":"interrupted","data":""}
```

On receipt, immediately stop current model playback and clear queued model
audio. Microphone capture may continue.

### Task 7: GoAway And Resumption

Activated only after the Task 7 PR merges.

```json
{"type":"go_away","data":{"time_left_ms":5000}}
```

```json
{"type":"session_resumption","data":{"resumable":true}}
```

The backend owns the opaque Gemini resumption handle and cloud reconnection.
The frontend must not persist or replay the handle.

## Frontend Compatibility Rules

- Implement the released protocol as the default behavior.
- Feature-gate planned messages until the corresponding backend PR merges.
- Never send media before `connected`.
- Reply to backend `ping` with `pong`.
- Treat unknown message types and status values defensively without crashing.
- Never include the Gemini API key in frontend code or browser storage.
