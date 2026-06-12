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
  behavior until the named backend PR has merged and that commit is deployed.
- Every backend PR that changes the protocol must update this document in the
  same PR.

The current backend does not provide runtime capability negotiation. The
deployment owner must publish the deployed backend commit SHA and protocol
stage in release metadata consumed by the frontend deployment. A merged PR is
not sufficient to enable a frontend feature.

Protocol stages:

| Stage | Available behavior |
|---:|---|
| 0 | Legacy protocol before bounded media |
| 1 | Released: bounded media validation |
| 2 | Released: bounded fair scheduler semantics |
| 3 | Released: explicit session lifecycle |
| 5 | Released: usage and budget events |
| 6 | Released: interruption event |
| 7 | Released: GoAway and transparent session resumption |

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

At protocol stage 3, the browser WebSocket and Gemini cloud session have
separate lifecycles:

1. Frontend opens the WebSocket.
2. Frontend sends `start_session` after explicit user action.
3. Backend creates Gemini Live and sends `status: connected`.
4. Frontend sends text, audio, and video messages.
5. Frontend sends `stop_session`, or the session reaches a terminal condition.
6. Backend sends a terminal status and releases Gemini Live.
7. The same browser WebSocket may start another cloud session.

Gemini Live is not created before a valid `start_session`. Before start, the
backend accepts `ping` and `pong`; other valid message types receive the
Chinese error `请先发送 start_session`.

### Client Start Session

```json
{"type":"start_session","data":""}
```

Sending this while a cloud session is already active is accepted as a no-op.

### Client Stop Session

```json
{"type":"stop_session","data":""}
```

User stop takes priority if a timeout completes in the same event-loop turn.

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
- `data` must be strict Base64.
- Maximum decoded size is 8,192 bytes by default.
- The decoded PCM16 byte count must be even.

Recommended frontend chunk duration is 20–40 ms.

### Client Video Frame

```json
{
  "type":"video_frame",
  "data":"<base64-jpeg>",
  "timestamp":1781234567890,
  "sequence":42
}
```

Requirements:

- `data` must be strict Base64 whose decoded bytes start with the JPEG SOI
  marker (`FF D8`) and end with the JPEG EOI marker (`FF D9`).
- This marker-envelope check does not verify that the bytes form a complete or
  decodable JPEG image.
- Maximum decoded size is 524,288 bytes by default.
- `timestamp` must be an integer Unix epoch timestamp in milliseconds.
- `sequence` must be an integer.
- `timestamp` may differ from backend time by at most 2,000 ms in either
  direction by default.

### Stage 2 Input Scheduling

At protocol stage 2:

- Audio and text use bounded queues, with default capacities of 32 audio
  chunks and 8 text messages.
- At most one blocked audio submission and one blocked text submission are
  retained by the WebSocket reader. Additional input of the same type may
  receive a Chinese backpressure error.
- Video is latest-only. A newer accepted `sequence` replaces the pending
  frame, and a sequence that does not exceed the highest previously accepted
  sequence is ignored.
- Text and audio are prioritized in bounded batches, while pending video is
  still guaranteed progress.
- WebSocket disconnect closes the scheduler, wakes blocked submitters, drains
  queued input within a hard timeout, and then closes the Gemini session.

### Server Connected Status

```json
{"type":"status","data":"connected"}
```

The frontend may begin sending media after this event.

### Server Terminal Status

```json
{"type":"status","data":"stopped"}
```

Terminal values:

| Value | Meaning | Frontend action |
|---|---|---|
| `stopped` | User stop or Gemini response stream ended naturally | Stop media; allow restart |
| `idle_timeout` | No validated and accepted input for 45 seconds by default | Stop media; allow restart |
| `max_duration` | Session reached 600 seconds by default | Stop media; allow restart |
| `budget_exceeded` | Gemini reported at least 50,000 total tokens by default | Stop media; allow restart |

The backend keeps the browser WebSocket open after a terminal status. Idle
time refreshes only after validated input is accepted by the scheduler.

### Stage 5 Usage And Budget

At protocol stage 5, every cloud session sends exactly one final `usage`
event after its terminal `status`:

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

- `audio_bytes`: audio bytes accepted by the input scheduler.
- `text_chars`: text characters accepted by the input scheduler.
- `video_frames`: video frames accepted by the latest-frame scheduler.
- `video_replaced_frames`: accepted frames that replaced a pending frame
  before cloud forwarding. Regressing or duplicate sequences are not accepted
  and are not counted.
- `video_bytes`: bytes across all accepted video frames, including frames
  later replaced before forwarding.
- `input_tokens`: sum of google-genai 2.8.0
  `UsageMetadata.prompt_token_count` values reported during the session.
- `output_tokens`: sum of google-genai 2.8.0
  `UsageMetadata.response_token_count` values reported during the session.
- `total_tokens`: sum of google-genai 2.8.0
  `UsageMetadata.total_token_count` values reported during the session.
- `duration_ms`: cloud-session duration measured by the backend.
- `first_response_latency_ms`: delay from the first accepted input to the
  first text or audio model output. It is `null` if either event never occurs.

`SESSION_TOKEN_BUDGET` is a required-positive configuration with a default of
50,000 tokens. The default is intentionally conservative enough for a
demonstrable session guard; it is an operational limit, not a billing
guarantee.

When `total_tokens >= SESSION_TOKEN_BUDGET`, the backend stops accepting and
sending input for that cloud session, closes the cloud session, then sends:

```json
{"type":"status","data":"budget_exceeded"}
```

The single final `usage` event follows that status. The browser WebSocket
remains open and may send `start_session` again; counters reset for the new
cloud session. The same status-then-usage ordering applies to `stopped`,
`idle_timeout`, and `max_duration`.

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

### Stage 6 Server Interruption

```json
{"type":"interrupted","data":""}
```

When Gemini reports an interruption, the backend emits this event at most
once for that Gemini service message and before any usage, text, audio, or
turn-complete event translated from the same message.

On receipt, immediately stop current model playback and clear queued model
audio. Microphone capture may continue.

### Stage 7 GoAway And Session Resumption

```json
{"type":"session_resumption","data":{"resumable":true}}
```

`data` contains only the current `resumable` flag. The backend keeps the
opaque Gemini handle in memory for the current browser WebSocket and never
sends it to the frontend.

```json
{"type":"go_away","data":{"time_left_ms":5000}}
```

`time_left_ms` is Gemini's remaining connection lifetime converted from the
google-genai 2.8.0 duration string to milliseconds.

After GoAway, the browser WebSocket stays open. The backend closes the current
Gemini connection and attempts at most one automatic reconnection using the
latest valid handle. If that resumed connection cannot be established, the
backend attempts one clean Gemini connection without a handle. It does not
retry either path indefinitely.

Automatic reconnection preserves the current logical session's runtime and
usage counters. The backend still emits exactly one final terminal `status`
and one final `usage` event. User stop, token budget exhaustion, idle timeout,
and maximum duration are terminal and never trigger automatic resumption.

### Server Turn Complete

```json
{"type":"turn_complete","data":""}
```

The current model response turn has finished. The frontend may use this event
to finalize transcript or playback UI state.

## Stage 2 Compatibility

Deployments reporting protocol stage 2 retain the pre-lifecycle behavior:
Gemini Live is created immediately, `start_session` and `stop_session` do not
exist, and ending the live session closes the browser WebSocket. Stage 2 still
provides the bounded fair scheduler documented above.

## Stage 1 Compatibility

Deployments reporting protocol stage 1 retain the pre-lifecycle behavior and
bounded media validation. Gemini Live is created immediately, and ending the
live session closes the browser WebSocket.

Deployments reporting protocol stage 1 provide bounded media validation but
do not promise stage 2 queue bounds, backpressure errors, latest-only video,
or fairness behavior.

## Stage 0 Compatibility

Deployments reporting protocol stage 0 use the pre-bounded-media contract:

- Audio allows up to 262,144 decoded bytes and does not enforce an even PCM16
  byte count.
- Video allows up to 2,097,152 decoded bytes and does not require JPEG
  markers, `timestamp`, or `sequence`.
- `start_session` and `stop_session` do not exist.
- Gemini Live is still created immediately and closing the live session still
  closes the browser WebSocket.

The frontend must select behavior from the deployment's `protocol_stage`.
Do not infer deployed capability from this repository's current branch or
GitHub merge state.

---

## Frontend Compatibility Rules

- Implement the released protocol as the default behavior.
- Feature-gate stage-specific messages using the protocol stage supplied by
  the deployment owner. Do not infer deployed capability from GitHub merge
  state.
- Never send media before `connected`.
- Reply to backend `ping` with `pong`.
- Treat unknown message types and status values defensively without crashing.
- Never include the Gemini API key in frontend code or browser storage.
