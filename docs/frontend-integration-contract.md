# Frontend Integration Contract

This document is the boundary between the backend repository and the separately developed frontend project.

## Ownership

The backend owns protocol validation, Gemini Live connectivity, scheduling, lifecycle limits, usage limits, and server events.

The frontend owns camera/microphone capture, PCM generation, JPEG sampling, playback, UI state, reconnection UX, and browser tests.

The frontend must not depend on backend Python modules. It should depend only on this WebSocket contract.

## Endpoint

Development endpoint:

```text
ws://localhost:8000/ws
```

All messages are UTF-8 JSON objects. Binary media is Base64-encoded in the `data` field.

## Session Lifecycle

The WebSocket connection and Gemini cloud session are separate:

1. Frontend opens the WebSocket.
2. Frontend sends `start_session` only after explicit user action.
3. Backend creates Gemini Live and sends `status: connected`.
4. Frontend sends text/audio/video messages.
5. Frontend sends `stop_session` to end cloud usage.
6. Backend sends `status: stopped`.
7. The same WebSocket may start another cloud session.

The frontend must not send media before `status: connected`.

## Client Messages

### Start Session

```json
{"type":"start_session","data":""}
```

Starts one Gemini Live session. Sending it while a session is already active has no additional effect.

### Stop Session

```json
{"type":"stop_session","data":""}
```

Stops only the active Gemini Live session. The browser WebSocket remains available for a later start.

### Ping

```json
{"type":"ping","data":""}
```

The backend replies with `pong`. This is valid before and during a cloud session.

### Pong

```json
{"type":"pong","data":""}
```

Reply to a backend `ping`. The backend accepts it silently.

### Text

```json
{"type":"text","data":"请描述镜头中的内容"}
```

Requirements:

- `data` is a non-empty string.
- Maximum length defaults to 2,000 characters.
- The backend may return a Chinese backpressure error when the text queue is full.

### Audio

```json
{"type":"audio","data":"<base64-pcm16>"}
```

Requirements:

- PCM signed 16-bit little-endian, mono.
- Base64 decoded byte count must be even.
- Maximum decoded size defaults to 8,192 bytes.
- Recommended frontend chunk duration is 20–40 ms.
- The backend may return a Chinese backpressure error when one audio submission is still pending.

### Video Frame

```json
{
  "type":"video_frame",
  "data":"<base64-jpeg>",
  "timestamp":1781234567890,
  "sequence":42
}
```

Requirements:

- `data` is a complete JPEG byte sequence.
- `timestamp` is Unix epoch time in milliseconds.
- `sequence` is an integer that increases for each captured frame.
- Maximum decoded size defaults to 524,288 bytes.
- Timestamp skew defaults to at most 2,000 ms in either direction.
- The backend keeps only the latest pending frame.
- The frontend should perform visual-change detection and adaptive sampling before upload.

## Server Messages

### Status

```json
{"type":"status","data":"connected"}
```

Defined status values:

| Value | Meaning | Frontend action |
|---|---|---|
| `connected` | Gemini Live session is ready | Enable media sending |
| `stopped` | Session ended normally or the model stream ended | Stop media sending |
| `idle_timeout` | No accepted input before the idle deadline | Show ended state; allow restart |
| `max_duration` | Maximum cloud-session duration reached | Show ended state; allow restart |
| `budget_exceeded` | Per-session token budget reached | Show cost-limit state; allow restart |

Unknown future status values must be treated as terminal for the current session without closing the browser WebSocket.

### Error

```json
{"type":"error","data":"视频帧已过期"}
```

Errors are Chinese user-facing strings. A protocol or backpressure error does not necessarily close the session.

### Ping And Pong

```json
{"type":"ping","data":""}
{"type":"pong","data":""}
```

Reply to `ping` with `pong`.

### Model Text Or Audio

Gemini response messages are forwarded as JSON objects by the backend service. The frontend should route text to the transcript and decoded audio to its playback queue according to the response `type`.

### Interrupted

Planned backend event:

```json
{"type":"interrupted","data":""}
```

On receipt, the frontend must immediately stop current playback and clear queued model audio. The frontend does not need to stop microphone capture.

### Usage

Planned backend event:

```json
{
  "type":"usage",
  "data":{
    "audio_bytes":32000,
    "video_frames":8,
    "video_bytes":180000,
    "input_tokens":1200,
    "output_tokens":340,
    "total_tokens":1540,
    "duration_ms":25000
  }
}
```

The frontend may display this data but must not use it as the source of truth for enforcing limits.

### GoAway

Planned backend event:

```json
{"type":"go_away","data":{"time_left_ms":5000}}
```

The backend owns cloud reconnection and resumption. The frontend should show a transient reconnecting state and continue using the same browser WebSocket.

### Session Resumption

Planned backend event:

```json
{"type":"session_resumption","data":{"resumable":true}}
```

The backend stores the opaque Gemini handle. The frontend must not persist or replay the handle.

## Frontend State Rules

- Open the microphone/camera according to product UX, but send media only after `connected`.
- Stop sending media after any terminal status.
- Clear model playback immediately on `interrupted`.
- Keep the browser WebSocket open after `stopped`, timeout, or budget exhaustion so the user can restart.
- Treat malformed or unknown messages defensively and log them without crashing the UI.
- Never include the Gemini API key in frontend code or browser storage.

## Backend Defaults

| Setting | Default |
|---|---:|
| Maximum audio bytes | 8,192 |
| Maximum video bytes | 524,288 |
| Maximum frame clock skew | 2,000 ms |
| Maximum text length | 2,000 characters |
| Audio queue capacity | 32 |
| Text queue capacity | 8 |
| Session idle timeout | 45 seconds |
| Session maximum duration | 600 seconds |
| WebSocket keepalive | 20 seconds |

Defaults may change through backend environment variables. The frontend should use server errors and statuses rather than hard-coding enforcement as authoritative.
