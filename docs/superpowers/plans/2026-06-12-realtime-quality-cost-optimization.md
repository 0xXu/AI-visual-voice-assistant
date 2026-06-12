# Backend Real-Time Quality And Cost Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve Gemini Live visual freshness, conversation latency, session reliability, and cost control entirely within the backend, while exposing a stable WebSocket contract for a separately developed frontend.

**Architecture:** The repository owns only the FastAPI backend. The backend validates and bounds client input, schedules audio/text/video fairly, controls Gemini Live sessions, reports usage and lifecycle events, and documents the WebSocket contract. Camera capture, microphone capture, PCM chunking, frame-difference detection, playback, and UI interruption behavior belong to the separate frontend project and are not implemented here.

**Tech Stack:** Python 3.11, FastAPI, asyncio, Google Gen AI SDK 2.x, Pydantic Settings, pytest, uv.

---

## Scope Boundary

### Backend Repository Owns

- WebSocket message parsing and validation.
- Explicit `start_session` and `stop_session` lifecycle.
- Bounded text/audio queues and latest-frame video scheduling.
- Gemini Live configuration, connection, response translation, and cleanup.
- Idle timeout, maximum session duration, usage accounting, and token budget.
- Server events for interruption, session ending, usage, GoAway, and resumption.
- A versioned frontend integration contract.
- Backend tests, operational defaults, and Chinese logs/errors.

### Frontend Project Owns

- Camera and microphone permission handling.
- PCM16 capture, resampling, and 20–40 ms audio chunk generation.
- JPEG capture, frame timestamps, sequence numbers, and visual-change sampling.
- Audio playback queue and immediate playback cancellation on interruption.
- Reconnection UI, status rendering, user controls, and browser compatibility.
- Frontend unit, browser, lint, and build tests.

The backend must not add a `frontend/` directory or frontend dependencies. Frontend behavior is specified only through `docs/frontend-integration-contract.md`.

---

## Pull Request Policy

Each task below is exactly one PR and must contain one independently reviewable function.

1. Create the task branch only after the previous PR has merged into `main`.
2. Branch from the latest remote `main`.
3. Do not combine two tasks in one branch or PR.
4. A PR may contain multiple commits for review fixes, but its diff must cover only its named task.
5. Every PR must keep `main` runnable and pass the full backend suite.
6. Every PR description must contain:
   - **标题**：一句话说明新增或修改的单一功能。
   - **功能描述**：说明作用、外部行为和使用方式。
   - **实现思路**：说明核心数据流、边界和技术选择。
   - **测试方式**：列出可复现命令和关键场景。
7. Do not open stacked PRs whose diff includes an unmerged predecessor. Merge PR N before creating PR N+1.

Required verification for every PR:

```bash
cd backend
uv sync --locked
uv run pytest -q
uv run python -m compileall -q app tests
```

---

## File Structure

- `backend/app/api/messages.py`: Parse and validate lifecycle, text, audio, and timestamped JPEG messages.
- `backend/app/api/websocket.py`: Own one browser WebSocket and repeated cloud-session lifecycles.
- `backend/app/core/config.py`: Define validated queue, timeout, budget, media, and session-management settings.
- `backend/app/services/input_scheduler.py`: Prioritize text/audio and retain only the newest video frame.
- `backend/app/services/session_runtime.py`: Enforce idle timeout, maximum duration, and token budget.
- `backend/app/services/gemini_service.py`: Configure Gemini Live and translate SDK events into application events.
- `backend/app/services/usage.py`: Aggregate bytes, frames, tokens, and latency metrics.
- `backend/tests/`: Unit and integration-style tests using fake Gemini sessions.
- `docs/frontend-integration-contract.md`: Stable protocol consumed by the separately developed frontend.

---

### Task 0: Document Backend And Frontend Separation

**PR title:** `docs: define backend and frontend integration boundary`

**Files:**
- Modify: `docs/superpowers/plans/2026-06-12-realtime-quality-cost-optimization.md`
- Create: `docs/frontend-integration-contract.md`

- [ ] **Step 1: Verify the plan has no frontend implementation paths**

Run:

```bash
rg -n 'frontend/(app|hooks|lib)' \
  docs/superpowers/plans/2026-06-12-realtime-quality-cost-optimization.md
```

Expected: no matches.

- [ ] **Step 2: Verify the integration contract documents every current client message**

Run:

```bash
rg -n 'ping|pong|audio|video_frame|text|turn_complete' \
  docs/frontend-integration-contract.md
```

Expected: all currently released message types are present. Planned lifecycle
messages are listed separately and marked with the PR that activates them.

- [ ] **Step 3: Run backend verification**

```bash
cd backend
uv run pytest -q
uv run python -m compileall -q app tests
```

Expected: all tests pass and compilation exits successfully.

- [ ] **Step 4: Commit and open one documentation-only PR**

```bash
git add docs/superpowers/plans/2026-06-12-realtime-quality-cost-optimization.md \
  docs/frontend-integration-contract.md
git commit -m "docs: define backend frontend boundary"
```

---

### Task 1: Add Bounded Real-Time Media Protocol

**PR title:** `feat: validate and bound realtime client media`

**Files:**
- Modify: `backend/app/api/messages.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`
- Modify: `backend/tests/test_messages.py`
- Modify: `backend/tests/test_config.py`
- Modify: `docs/frontend-integration-contract.md`

- [ ] **Step 1: Write failing protocol tests**

Cover:

```python
def test_rejects_oversized_audio_before_decode(settings): ...
def test_rejects_odd_length_pcm16(settings): ...
def test_rejects_non_jpeg_video(settings): ...
def test_rejects_stale_and_future_video_timestamps(settings): ...
def test_parses_bounded_text_messages(settings): ...
```

- [ ] **Step 2: Run focused tests and verify failure**

```bash
cd backend
uv run pytest tests/test_messages.py tests/test_config.py -q
```

Expected: new validation cases fail before implementation.

- [ ] **Step 3: Implement the bounded parser**

Requirements:

- Decode Base64 with strict validation.
- Reject encoded payloads that cannot fit the configured decoded limit before allocating decoded bytes.
- Require PCM16 audio to contain an even byte count.
- Require JPEG start/end markers.
- Require integer `timestamp` and `sequence`.
- Reject frames older or further in the future than `MAX_FRAME_AGE_MS`.
- Return Chinese client-facing errors.

- [ ] **Step 4: Verify and commit**

```bash
uv run pytest -q
uv run python -m compileall -q app tests
git add backend/app/api/messages.py backend/app/core/config.py \
  backend/.env.example backend/tests/test_messages.py backend/tests/test_config.py \
  docs/frontend-integration-contract.md
git commit -m "feat: add bounded realtime media protocol"
```

---

### Task 2: Add Bounded Fair Input Scheduler

**PR title:** `feat: prioritize audio and retain the latest video frame`

**Files:**
- Create: `backend/app/services/input_scheduler.py`
- Create: `backend/tests/test_input_scheduler.py`
- Modify: `backend/app/api/websocket.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`
- Modify: `docs/frontend-integration-contract.md`

- [ ] **Step 1: Write failing scheduler tests**

Cover:

```python
async def test_audio_and_text_are_bounded(): ...
async def test_new_video_replaces_pending_video(): ...
async def test_regressing_video_sequence_is_rejected(): ...
async def test_video_is_not_starved_by_continuous_audio(): ...
async def test_stop_remains_responsive_when_queues_are_full(): ...
async def test_close_is_race_safe_and_has_a_hard_timeout(): ...
```

- [ ] **Step 2: Run focused tests and verify failure**

```bash
cd backend
uv run pytest tests/test_input_scheduler.py -q
```

- [ ] **Step 3: Implement scheduler semantics**

Requirements:

- Audio and text use bounded queues.
- Video stores only the newest accepted sequence.
- Scheduling favors text/audio but guarantees periodic video progress.
- Queue saturation applies bounded backpressure.
- Shutdown wakes blocked producers, propagates drain failures, and has a hard timeout.
- The WebSocket remains the only task reading client messages.

- [ ] **Step 4: Verify and commit**

```bash
uv run pytest -q
uv run python -m compileall -q app tests
git add backend/app/services/input_scheduler.py \
  backend/tests/test_input_scheduler.py backend/app/api/websocket.py \
  backend/app/core/config.py backend/.env.example \
  docs/frontend-integration-contract.md
git commit -m "feat: add bounded fair input scheduler"
```

---

### Task 3: Add Explicit Session Lifecycle And Limits

**PR title:** `feat: enforce explicit realtime session lifecycle`

**Files:**
- Create: `backend/app/services/session_runtime.py`
- Create: `backend/tests/test_session_runtime.py`
- Modify: `backend/app/api/messages.py`
- Modify: `backend/app/api/websocket.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`
- Modify: `backend/tests/test_websocket.py`
- Modify: `backend/tests/test_config.py`
- Modify: `docs/frontend-integration-contract.md`

- [ ] **Step 1: Write failing lifecycle tests**

Cover:

```python
async def test_gemini_is_not_created_before_start(): ...
def test_parses_start_and_stop_lifecycle_messages(): ...
async def test_pre_start_ping_pong_is_supported(): ...
async def test_stop_returns_stopped_and_allows_another_session(): ...
async def test_only_successfully_enqueued_input_refreshes_idle_time(): ...
async def test_idle_and_max_duration_return_distinct_statuses(): ...
async def test_user_stop_wins_when_timeout_completes_same_turn(): ...
async def test_cleanup_has_a_hard_upper_bound(): ...
def test_timeout_settings_require_positive_values(): ...
```

- [ ] **Step 2: Run focused tests and verify failure**

```bash
cd backend
uv run pytest tests/test_session_runtime.py tests/test_websocket.py \
  tests/test_config.py -q
```

- [ ] **Step 3: Implement lifecycle behavior**

Requirements:

- Use monotonic time.
- Default idle timeout is 45 seconds; maximum duration is 600 seconds.
- Validate both values as positive during settings construction.
- Do not instantiate Gemini before a valid `start_session`.
- Support repeated start/stop cycles on one WebSocket.
- Refresh idle only after a validated input is accepted by the scheduler.
- User stop takes priority over a simultaneous timeout.
- Natural Gemini stream ending emits a terminal status.
- Cancellation and task observation have a hard cleanup deadline.

- [ ] **Step 4: Stabilize timing tests**

Use an injected clock or event-controlled waits for expiry decisions. Do not depend on 10–60 ms wall-clock windows for core assertions.

- [ ] **Step 5: Verify and commit**

```bash
uv run pytest -q
uv run python -m compileall -q app tests
git add backend/app/services/session_runtime.py backend/app/api/messages.py \
  backend/tests/test_session_runtime.py backend/app/api/websocket.py \
  backend/app/core/config.py backend/.env.example \
  backend/tests/test_websocket.py backend/tests/test_config.py \
  docs/frontend-integration-contract.md
git commit -m "feat: enforce realtime session lifecycle"
```

---

### Task 4: Add Cost-Safe Gemini Live Configuration

**PR title:** `feat: configure low-cost Gemini Live defaults`

**Files:**
- Modify: `backend/app/services/gemini_service.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`
- Modify: `backend/tests/test_gemini_service.py`
- Modify: `backend/tests/test_config.py`

- [ ] **Step 1: Write failing configuration tests**

Cover:

```python
def test_build_live_config_uses_low_media_resolution(): ...
def test_build_live_config_enables_sliding_window_compression(): ...
def test_live_cost_settings_have_validated_defaults(): ...
```

- [ ] **Step 2: Implement one pure config builder**

Create `build_live_config(settings)` and set:

- audio response modality;
- configured voice;
- low media resolution;
- sliding-window context compression;
- existing Chinese system instruction.

Keep Google AI Studio API-key authentication only. Do not add Vertex AI settings.

- [ ] **Step 3: Verify and commit**

```bash
cd backend
uv run pytest -q
uv run python -m compileall -q app tests
git add backend/app/services/gemini_service.py backend/app/core/config.py \
  backend/.env.example backend/tests/test_gemini_service.py \
  backend/tests/test_config.py
git commit -m "feat: configure cost safe Gemini Live defaults"
```

---

### Task 5: Add Usage Accounting And Session Token Budget

**PR title:** `feat: enforce per-session usage budget`

**Files:**
- Create: `backend/app/services/usage.py`
- Create: `backend/tests/test_usage.py`
- Modify: `backend/app/services/session_runtime.py`
- Modify: `backend/app/services/gemini_service.py`
- Modify: `backend/app/api/websocket.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`
- Modify: `backend/tests/test_websocket.py`
- Modify: `docs/frontend-integration-contract.md`

- [ ] **Step 1: Write failing accounting tests**

Cover byte/frame counters, token accumulation, latency calculation, budget exhaustion, and one final usage event.

- [ ] **Step 2: Implement `SessionUsage`**

Use a focused dataclass that records:

- accepted audio bytes;
- accepted text characters;
- accepted/replaced video frames and bytes;
- input/output/total tokens from Gemini usage metadata;
- session duration and response latency.

- [ ] **Step 3: Enforce the budget**

When total tokens reach `SESSION_TOKEN_BUDGET`, stop forwarding new input, send:

```json
{"type":"status","data":"budget_exceeded"}
```

Then send one structured usage event and close only the cloud session, leaving the browser WebSocket ready for a later `start_session`.

- [ ] **Step 4: Verify and commit**

```bash
cd backend
uv run pytest -q
uv run python -m compileall -q app tests
git add backend/app/services/usage.py backend/tests/test_usage.py \
  backend/app/services/session_runtime.py \
  backend/app/services/gemini_service.py backend/app/api/websocket.py \
  backend/app/core/config.py backend/.env.example \
  backend/tests/test_websocket.py docs/frontend-integration-contract.md
git commit -m "feat: enforce per session usage budget"
```

---

### Task 6: Forward Server Interruption Events

**PR title:** `feat: expose Gemini interruption events to clients`

**Files:**
- Modify: `backend/app/services/gemini_service.py`
- Modify: `backend/tests/test_gemini_service.py`
- Modify: `docs/frontend-integration-contract.md`

- [ ] **Step 1: Write a failing event-translation test**

Given a Gemini server message with `server_content.interrupted == true`, expect:

```json
{"type":"interrupted","data":""}
```

- [ ] **Step 2: Implement the backend translation**

The backend only forwards the event. The separate frontend is responsible for immediately stopping and clearing queued audio playback.

- [ ] **Step 3: Verify and commit**

```bash
cd backend
uv run pytest -q
uv run python -m compileall -q app tests
git add backend/app/services/gemini_service.py \
  backend/tests/test_gemini_service.py docs/frontend-integration-contract.md
git commit -m "feat: expose Gemini interruption events"
```

---

### Task 7: Add Session Resumption And GoAway Events

**PR title:** `feat: support Gemini session resumption signals`

**Files:**
- Modify: `backend/app/services/gemini_service.py`
- Modify: `backend/app/api/websocket.py`
- Modify: `backend/tests/test_gemini_service.py`
- Modify: `backend/tests/test_websocket.py`
- Modify: `docs/frontend-integration-contract.md`

- [ ] **Step 1: Write failing translation and lifecycle tests**

Cover:

```python
def test_translates_resumption_handle(): ...
def test_translates_go_away_deadline(): ...
async def test_next_cloud_session_reuses_latest_handle(): ...
async def test_invalid_handle_falls_back_to_clean_session(): ...
```

- [ ] **Step 2: Implement backend session management**

- Enable transparent session resumption in the Live configuration.
- Store only the latest valid resumption handle for the current browser WebSocket.
- Emit `session_resumption` and `go_away` events to the client.
- Attempt one resumed connection after GoAway.
- Fall back to a clean session when resumption is rejected.

- [ ] **Step 3: Verify and commit**

```bash
cd backend
uv run pytest -q
uv run python -m compileall -q app tests
git add backend/app/services/gemini_service.py backend/app/api/websocket.py \
  backend/tests/test_gemini_service.py backend/tests/test_websocket.py \
  docs/frontend-integration-contract.md
git commit -m "feat: support Gemini session resumption"
```

---

### Task 8: Document And Verify Backend Operational Defaults

**PR title:** `docs: document backend realtime operations`

**Files:**
- Modify: `README.md`
- Modify: `backend/.env.example`
- Modify: `docs/frontend-integration-contract.md`

- [ ] **Step 1: Document backend-only setup**

The README must show:

```bash
cd backend
uv sync --locked
cp .env.example .env
uv run uvicorn app.main:app --reload
```

Document Google AI Studio `GEMINI_API_KEY`, all queue/media/session/budget defaults, WebSocket endpoint, and test commands. Do not document Docker, Cloud Build, Vertex AI, or frontend build commands.

- [ ] **Step 2: Verify secrets and Chinese runtime output**

```bash
rg -n 'AQ\.[A-Za-z0-9_-]{20,}|AIza[A-Za-z0-9_-]{20,}' . \
  -g '!backend/.env' -g '!.git/**' -g '!docs/superpowers/plans/**'
rg -n '\\bprint\\s*\\(' backend/app
```

Expected: no real API key and no backend `print()` calls.

- [ ] **Step 3: Run final backend verification**

```bash
cd backend
uv sync --locked
uv run pytest -q
uv run python -m compileall -q app tests
```

- [ ] **Step 4: Commit**

```bash
git add README.md backend/.env.example docs/frontend-integration-contract.md
git commit -m "docs: document backend realtime operations"
```

---

## PR Sequence

Merge strictly in this order:

1. Task 0: Backend/frontend boundary documentation
2. Task 1: Bounded media protocol
3. Task 2: Bounded fair scheduler
4. Task 3: Explicit session lifecycle
5. Task 4: Cost-safe Gemini configuration
6. Task 5: Usage accounting and token budget
7. Task 6: Interruption event
8. Task 7: Session resumption and GoAway
9. Task 8: Operational documentation

Task 1–3 code currently exists only as preparatory commits on a temporary branch. Those commits must be replayed into separate branches after Task 0 merges; the temporary combined branch must not be opened as a PR.
