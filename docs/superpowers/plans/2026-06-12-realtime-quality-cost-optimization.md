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
- A release-aware frontend integration contract.
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

Each task below is exactly one PR and must deliver only that named task's
coherent capability or documentation outcome. "One task" means one reviewable
product behavior, not one Python function.

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
(cd backend && uv sync --locked)
(cd backend && uv run pytest -q)
(cd backend && uv run python -m compileall -q app tests)
```

All commands in this plan start from the repository root. Parenthesized
backend commands do not change the shell's working directory.

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

**PR title:** `docs: 明确后端与前端独立开发边界`

**Files:**
- Modify: `docs/superpowers/plans/2026-06-12-realtime-quality-cost-optimization.md`
- Create: `docs/frontend-integration-contract.md`

- [x] **Step 1: Verify the plan has no frontend implementation paths**

Run:

```bash
rg -n 'frontend/(app|hooks|lib)' \
  docs/superpowers/plans/2026-06-12-realtime-quality-cost-optimization.md
```

Expected: no matches.

- [x] **Step 2: Verify the Released Protocol contains every current message heading**

Run:

```bash
released="$(mktemp)"
sed -n '/^## Released Protocol$/,/^## Planned Protocol Evolution$/p' \
  docs/frontend-integration-contract.md > "$released"
for heading in \
  "Client Ping" "Client Pong" "Client Text" "Client Audio" \
  "Client Video Frame" "Server Connected Status" "Server Error" \
  "Server Keepalive Ping" "Server Text" "Server Audio" \
  "Server Turn Complete"; do
  rg -q "^### ${heading}$" "$released" || exit 1
done
rm "$released"
```

Expected: exit status 0. Planned lifecycle messages are outside the extracted
Released Protocol section.

- [x] **Step 3: Run backend verification**

```bash
(cd backend && uv run pytest -q)
(cd backend && uv run python -m compileall -q app tests)
```

Expected: all tests pass and compilation exits successfully.

- [x] **Step 4: Commit and open one documentation-only PR**

```bash
git add docs/superpowers/plans/2026-06-12-realtime-quality-cost-optimization.md \
  docs/frontend-integration-contract.md
git commit -m "docs: define backend frontend boundary"
```

---

### Task 1: Add Bounded Real-Time Media Protocol

**PR title:** `feat: 校验并限制实时媒体输入`

**Files:**
- Modify: `backend/app/api/messages.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`
- Modify: `backend/tests/test_messages.py`
- Modify: `backend/tests/test_config.py`
- Modify: `backend/tests/test_websocket.py`
- Create: `backend/tests/conftest.py`
- Modify: `docs/frontend-integration-contract.md`
- Modify: `docs/superpowers/plans/2026-06-12-realtime-quality-cost-optimization.md`

- [x] **Step 1: Write failing protocol tests**

Cover:

```python
def test_rejects_oversized_audio_before_decode(settings): ...
def test_rejects_odd_length_pcm16(settings): ...
def test_rejects_video_without_jpeg_soi_eoi_markers(settings): ...
def test_rejects_stale_and_future_video_timestamps(settings): ...
def test_parses_bounded_text_messages(settings): ...
```

- [x] **Step 2: Run focused tests and verify failure**

```bash
(cd backend && uv run pytest tests/test_messages.py tests/test_config.py -q)
```

Expected: new validation cases fail before implementation.

- [x] **Step 3: Implement the bounded parser**

Requirements:

- Decode Base64 with strict validation.
- Reject encoded payloads that cannot fit the configured decoded limit before allocating decoded bytes.
- Require PCM16 audio to contain an even byte count.
- Require a JPEG marker envelope: SOI at the start and EOI at the end.
- Do not claim or perform complete JPEG decoding or structural validation.
- Require integer `timestamp` and `sequence`.
- Reject frames older or further in the future than `MAX_FRAME_AGE_MS`.
- Return Chinese client-facing errors.

- [x] **Step 4: Verify and commit**

```bash
(cd backend && uv run pytest -q)
(cd backend && uv run python -m compileall -q app tests)
git add backend/app/api/messages.py backend/app/core/config.py \
  backend/.env.example backend/tests/test_messages.py backend/tests/test_config.py \
  backend/tests/test_websocket.py backend/tests/conftest.py \
  docs/frontend-integration-contract.md \
  docs/superpowers/plans/2026-06-12-realtime-quality-cost-optimization.md
git commit -m "feat: add bounded realtime media protocol"
```

---

### Task 2: Add Bounded Fair Input Scheduler

**PR title:** `feat: 增加有界公平实时输入调度器`

**Files:**
- Create: `backend/app/services/input_scheduler.py`
- Create: `backend/tests/test_input_scheduler.py`
- Modify: `backend/app/api/websocket.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`
- Modify: `backend/tests/test_config.py`
- Modify: `backend/tests/test_websocket.py`
- Modify: `docs/frontend-integration-contract.md`
- Modify: `docs/superpowers/plans/2026-06-12-realtime-quality-cost-optimization.md`

- [x] **Step 1: Write failing scheduler tests**

Cover:

```python
async def test_audio_and_text_are_bounded(): ...
async def test_new_video_replaces_pending_video(): ...
async def test_regressing_video_sequence_is_rejected(): ...
async def test_video_is_not_starved_by_continuous_audio(): ...
async def test_reader_remains_responsive_when_queues_are_full(): ...
async def test_close_is_race_safe_and_has_a_hard_timeout(): ...
```

- [x] **Step 2: Run focused tests and verify failure**

```bash
(cd backend && uv run pytest tests/test_input_scheduler.py \
  tests/test_websocket.py tests/test_config.py -q)
```

- [x] **Step 3: Implement scheduler semantics**

Requirements:

- Audio and text use bounded queues.
- Video stores only the newest accepted sequence.
- Scheduling favors text/audio but guarantees periodic video progress.
- Queue saturation applies bounded backpressure.
- Shutdown wakes blocked producers, propagates drain failures, and has a hard timeout.
- The WebSocket remains the only task reading client messages.

- [x] **Step 4: Verify and commit**

```bash
(cd backend && uv run pytest -q)
(cd backend && uv run python -m compileall -q app tests)
git add backend/app/services/input_scheduler.py \
  backend/tests/test_input_scheduler.py backend/app/api/websocket.py \
  backend/app/core/config.py backend/.env.example backend/tests/test_config.py \
  backend/tests/test_websocket.py docs/frontend-integration-contract.md \
  docs/superpowers/plans/2026-06-12-realtime-quality-cost-optimization.md
git commit -m "feat: add bounded fair input scheduler"
```

---

### Task 3: Add Explicit Session Lifecycle And Limits

**PR title:** `feat: 发布显式会话生命周期与超时清理`

**Files:**
- Create: `backend/app/services/session_runtime.py`
- Create: `backend/tests/test_session_runtime.py`
- Modify: `backend/app/api/messages.py`
- Modify: `backend/app/api/websocket.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`
- Modify: `backend/tests/conftest.py`
- Modify: `backend/tests/test_messages.py`
- Modify: `backend/tests/test_websocket.py`
- Modify: `backend/tests/test_config.py`
- Modify: `docs/frontend-integration-contract.md`
- Modify: `docs/superpowers/plans/2026-06-12-realtime-quality-cost-optimization.md`

- [x] **Step 1: Write failing lifecycle tests**

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

- [x] **Step 2: Run focused tests and verify failure**

```bash
(cd backend && uv run pytest tests/test_session_runtime.py \
  tests/test_websocket.py tests/test_config.py -q)
```

- [x] **Step 3: Implement lifecycle behavior**

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

- [x] **Step 4: Stabilize timing tests**

Use an injected clock or event-controlled waits for expiry decisions. Do not depend on 10–60 ms wall-clock windows for core assertions.

- [x] **Step 5: Verify and commit**

```bash
(cd backend && uv run pytest -q)
(cd backend && uv run python -m compileall -q app tests)
git add backend/app/services/session_runtime.py backend/app/api/messages.py \
  backend/tests/test_session_runtime.py backend/tests/test_messages.py \
  backend/app/api/websocket.py backend/app/core/config.py backend/.env.example \
  backend/tests/conftest.py \
  backend/tests/test_websocket.py backend/tests/test_config.py \
  docs/frontend-integration-contract.md \
  docs/superpowers/plans/2026-06-12-realtime-quality-cost-optimization.md
git commit -m "feat: enforce realtime session lifecycle"
```

---

### Task 4: Add Cost-Safe Gemini Live Configuration

**PR title:** `feat: 配置 Gemini Live 成本安全默认值`

**Files:**
- Modify: `backend/app/services/gemini_service.py`
- Modify: `backend/tests/test_gemini_service.py`
- Modify: `docs/superpowers/plans/2026-06-12-realtime-quality-cost-optimization.md`

- [x] **Step 1: Write focused failing configuration tests**

Cover:

```python
def test_build_live_config_uses_cost_safe_live_defaults(): ...
def test_connect_uses_live_config_builder(): ...
```

- [x] **Step 2: Implement one pure config builder**

Create `build_live_config(settings)` and set:

- audio response modality;
- configured voice;
- low media resolution;
- sliding-window context compression;
- existing Chinese system instruction;
- existing input/output transcription and automatic activity detection.

Keep Google AI Studio API-key authentication only. Do not add alternative
cloud authentication settings.
The installed `google-genai` 2.x types make compression token thresholds
optional, so this task does not add speculative environment settings or change
`backend/.env.example`.

- [x] **Step 3: Verify and commit**

```bash
(cd backend && uv run pytest -q tests/test_gemini_service.py)
(cd backend && uv run pytest -q)
(cd backend && uv run python -m compileall -q app tests)
git add backend/app/services/gemini_service.py \
  backend/tests/test_gemini_service.py \
  docs/superpowers/plans/2026-06-12-realtime-quality-cost-optimization.md
git commit -m "feat: 配置 Gemini Live 成本安全默认值"
```

This task does not change the WebSocket wire protocol, so
`docs/frontend-integration-contract.md` requires no update.

---

### Task 5: Add Usage Accounting And Session Token Budget

**PR title:** `feat: enforce per-session usage budget`

**Files:**
- Create: `backend/app/services/usage.py`
- Create: `backend/tests/test_usage.py`
- Modify: `backend/app/services/gemini_service.py`
- Modify: `backend/app/services/input_scheduler.py`
- Modify: `backend/app/api/websocket.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`
- Modify: `backend/tests/test_gemini_service.py`
- Modify: `backend/tests/test_config.py`
- Modify: `backend/tests/test_websocket.py`
- Modify: `docs/frontend-integration-contract.md`
- Modify: `README.md`

- [x] **Step 1: Write failing accounting tests**

Cover byte/frame counters, token accumulation, latency calculation, budget
exhaustion, one final usage event, and repeated-session counter reset.

- [x] **Step 2: Implement `SessionUsage`**

Use a focused dataclass that records:

- accepted audio bytes;
- accepted text characters;
- accepted/replaced video frames and bytes;
- input/output/total tokens from Gemini usage metadata;
- session duration and response latency.

google-genai 2.8.0 exposes these fields through the real
`types.LiveServerMessage.usage_metadata: types.UsageMetadata | None` type:

- `prompt_token_count`;
- `response_token_count`;
- `total_token_count`.

The latest-frame scheduler returns whether a newly accepted frame replaced a
pending frame, so replacement counts do not rely on inferred timing.

- [x] **Step 3: Enforce the budget**

When total tokens reach `SESSION_TOKEN_BUDGET`, stop forwarding new input, send:

```json
{"type":"status","data":"budget_exceeded"}
```

Then send one structured usage event and close only the cloud session, leaving the browser WebSocket ready for a later `start_session`.

- [x] **Step 4: Verify and commit**

```bash
(cd backend && uv run pytest -q tests/test_usage.py \
  tests/test_gemini_service.py tests/test_websocket.py \
  tests/test_config.py tests/test_input_scheduler.py)
(cd backend && uv run pytest -q)
(cd backend && uv run python -m compileall -q app tests)
git add backend/app/services/usage.py backend/tests/test_usage.py \
  backend/app/services/gemini_service.py \
  backend/app/services/input_scheduler.py backend/app/api/websocket.py \
  backend/app/core/config.py backend/.env.example \
  backend/tests/test_gemini_service.py backend/tests/test_config.py \
  backend/tests/test_input_scheduler.py backend/tests/test_websocket.py \
  docs/frontend-integration-contract.md \
  docs/superpowers/plans/2026-06-12-realtime-quality-cost-optimization.md \
  README.md
git commit -m "feat: 增加会话用量统计与 token 预算"
```

---

### Task 6: Forward Server Interruption Events

**PR title:** `feat: 转发 Gemini 用户打断事件`

**Files:**
- Modify: `backend/app/services/gemini_service.py`
- Modify: `backend/tests/test_gemini_service.py`
- Modify: `docs/frontend-integration-contract.md`
- Modify: `docs/superpowers/plans/2026-06-12-realtime-quality-cost-optimization.md`

- [x] **Step 1: Verify the SDK type and write failing translation tests**

In google-genai 2.8.0, `LiveServerContent.interrupted` is
`Optional[bool]` with a default of `None`.

Given a Gemini server message with `server_content.interrupted == true`,
expect exactly one:

```json
{"type":"interrupted","data":""}
```

Also cover `false` and verify interruption precedes usage, text, audio, and
turn-complete events translated from the same service message.

- [x] **Step 2: Implement the backend translation**

The backend only forwards the event, before other outputs from the same
service message. The separate frontend is responsible for immediately
stopping and clearing queued model audio; microphone capture may continue.

- [x] **Step 3: Verify and commit**

```bash
(cd backend && uv run pytest -q tests/test_gemini_service.py -k interruption)
(cd backend && uv run pytest -q)
(cd backend && uv run python -m compileall -q app tests)
git add backend/app/services/gemini_service.py \
  backend/tests/test_gemini_service.py docs/frontend-integration-contract.md \
  docs/superpowers/plans/2026-06-12-realtime-quality-cost-optimization.md
git commit -m "feat: 转发 Gemini 用户打断事件"
```

---

### Task 7: Add Session Resumption And GoAway Events

**PR title:** `feat: 支持 Gemini 会话恢复与 GoAway`

**Files:**
- Modify: `backend/app/services/gemini_service.py`
- Modify: `backend/app/api/websocket.py`
- Modify: `backend/tests/test_gemini_service.py`
- Modify: `backend/tests/test_websocket.py`
- Modify: `docs/frontend-integration-contract.md`
- Modify: `docs/superpowers/plans/2026-06-12-realtime-quality-cost-optimization.md`

- [x] **Step 1: Write failing translation and lifecycle tests**

Cover:

```python
def test_build_live_config_includes_resume_handle(): ...
def test_translates_resumption_update_without_exposing_handle(): ...
def test_translates_go_away_deadline_to_milliseconds(): ...
def test_go_away_reconnects_once_with_latest_handle(): ...
def test_failed_resume_falls_back_once_to_clean_session(): ...
def test_user_stop_does_not_trigger_resumption(): ...
```

- [x] **Step 2: Implement backend session management**

- Enable transparent session resumption in the Live configuration.
- Store only the latest valid resumption handle for the current browser WebSocket.
- Emit `session_resumption` with only `resumable`; never expose the opaque handle.
- Emit `go_away` with the remaining connection lifetime in milliseconds.
- Attempt one resumed connection after GoAway.
- Fall back to a clean session when resumption is rejected.
- Preserve logical-session runtime and usage across cloud reconnections.
- Do not resume after user stop, budget exhaustion, idle timeout, or maximum duration.

- [x] **Step 3: Verify and commit**

```bash
(cd backend && uv run pytest -q)
(cd backend && uv run python -m compileall -q app tests)
git add backend/app/services/gemini_service.py backend/app/api/websocket.py \
  backend/tests/test_gemini_service.py backend/tests/test_websocket.py \
  docs/frontend-integration-contract.md \
  docs/superpowers/plans/2026-06-12-realtime-quality-cost-optimization.md
git commit -m "feat: 支持 Gemini 会话恢复与 GoAway"
```

---

### Task 8: Document And Verify Backend Operational Defaults

**PR title:** `docs: 完善后端实时会话运维说明`

**Files:**
- Modify: `README.md`
- Verify unchanged: `backend/.env.example`
- Modify: `docs/superpowers/plans/2026-06-12-realtime-quality-cost-optimization.md`

- [x] **Step 1: Document backend-only setup**

The README must show:

```bash
cd backend
uv sync --locked
cp .env.example .env
uv run uvicorn app.main:app --reload
```

Document Google AI Studio `GEMINI_API_KEY`, all queue/media/session/budget
defaults, WebSocket endpoint, and test commands. Keep deployment systems and
frontend build instructions out of this backend operations guide.

- [x] **Step 2: Verify secrets and Chinese runtime output**

```bash
rg -n 'AIza[0-9A-Za-z_-]{35}' . \
  -g '!backend/.env' -g '!.git/**' -g '!docs/superpowers/plans/**'
rg -n '\\bprint\\s*\\(' backend/app
```

Expected: no real API key and no backend `print()` calls.

- [x] **Step 3: Run final backend verification**

```bash
(cd backend && uv sync --locked)
(cd backend && uv run pytest -q)
(cd backend && uv run python -m compileall -q app tests)
```

- [x] **Step 4: Commit**

```bash
git add README.md \
  docs/superpowers/plans/2026-06-12-realtime-quality-cost-optimization.md
git commit -m "docs: 完善后端实时会话运维说明"
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

Tasks 0–7 have merged as separate functional PRs. Task 8 is the final
documentation-only PR.
