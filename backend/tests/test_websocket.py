import asyncio
import base64
import json
from contextlib import asynccontextmanager

import pytest
from fastapi import WebSocketDisconnect
from google.genai import types
from starlette.websockets import WebSocketState

from app.api import messages, websocket as websocket_api
from app.api.websocket import (
    SessionEndReason,
    _forward_client_messages,
    _run_session,
    _serve_websocket,
    _wait_for_start,
)
from app.services.input_scheduler import InputScheduler
from app.services.gemini_service import GeminiResponse
from app.services.session_runtime import (
    SessionIdleTimeout,
    SessionLifetimeExceeded,
)
from app.services.usage import SessionUsage


class FakeWebSocket:
    client_state = WebSocketState.CONNECTED

    def __init__(self, messages):
        self.messages = iter(messages)
        self.sent = []
        self.accepted = False
        self.closed = False

    async def accept(self):
        self.accepted = True

    async def receive_text(self):
        try:
            return next(self.messages)
        except StopIteration as exc:
            raise WebSocketDisconnect() from exc

    async def send_json(self, payload):
        self.sent.append(payload)

    async def close(self):
        self.closed = True
        self.client_state = WebSocketState.DISCONNECTED


class RecordingSession:
    def __init__(self):
        self.calls = []

    async def send_audio(self, data):
        self.calls.append(("audio", data))

    async def send_video_frame(self, data):
        self.calls.append(("video", data))

    async def send_text(self, data):
        self.calls.append(("text", data))

    async def receive(self):
        await asyncio.Event().wait()
        yield


class FakeService:
    model = "fake-live-model"

    def __init__(self, session):
        self.session = session
        self.released = False

    @asynccontextmanager
    async def connect(self, resume_handle=None):
        try:
            yield self.session
        finally:
            self.released = True


def test_forwards_ping_and_multimodal_messages(monkeypatch):
    async def scenario():
        fixed_now_ms = 10_000
        monkeypatch.setattr(
            messages.time,
            "time_ns",
            lambda: fixed_now_ms * 1_000_000,
        )
        encoded = base64.b64encode(b"data").decode("ascii")
        jpeg = b"\xff\xd8data\xff\xd9"
        encoded_jpeg = base64.b64encode(jpeg).decode("ascii")
        websocket = FakeWebSocket([
            json.dumps({"type": "ping", "data": ""}),
            json.dumps({"type": "audio", "data": encoded}),
            json.dumps({
                "type": "video_frame",
                "data": encoded_jpeg,
                "timestamp": fixed_now_ms,
                "sequence": 1,
            }),
            json.dumps({"type": "text", "data": "  请描述画面  "}),
        ])
        scheduler = InputScheduler(audio_capacity=4)
        session = RecordingSession()

        with pytest.raises(WebSocketDisconnect):
            await _forward_client_messages(websocket, scheduler)
        await scheduler.close()
        await scheduler.run(session)

        assert websocket.sent == [{"type": "pong", "data": ""}]
        assert session.calls == [
            ("text", "请描述画面"),
            ("audio", b"data"),
            ("video", jpeg),
        ]

    asyncio.run(scenario())


def test_returns_chinese_error_and_continues_after_invalid_message():
    async def scenario():
        websocket = FakeWebSocket([
            json.dumps({"type": "audio", "data": "%%%"}),
            json.dumps({"type": "text", "data": "继续"}),
        ])
        scheduler = InputScheduler(audio_capacity=4)
        session = RecordingSession()

        with pytest.raises(WebSocketDisconnect):
            await _forward_client_messages(websocket, scheduler)
        await scheduler.close()
        await scheduler.run(session)

        assert websocket.sent == [{
            "type": "error",
            "data": "媒体内容不是有效的 Base64 数据",
        }]
        assert session.calls == [("text", "继续")]

    asyncio.run(scenario())


def test_continues_after_json_parser_value_error():
    async def scenario():
        websocket = FakeWebSocket([
            '{"type":' + "9" * 5_000 + "}",
            json.dumps({"type": "text", "data": "继续"}),
        ])
        scheduler = InputScheduler(audio_capacity=4)
        session = RecordingSession()

        with pytest.raises(WebSocketDisconnect):
            await _forward_client_messages(websocket, scheduler)
        await scheduler.close()
        await scheduler.run(session)

        assert websocket.sent == [{
            "type": "error",
            "data": "消息不是有效的 JSON",
        }]
        assert session.calls == [("text", "继续")]

    asyncio.run(scenario())


def test_reader_remains_responsive_when_submission_is_blocked():
    async def scenario():
        scheduler = InputScheduler(audio_capacity=1)
        await scheduler.submit_audio(b"queued")
        encoded = base64.b64encode(b"data").decode("ascii")
        websocket = FakeWebSocket([
            json.dumps({"type": "audio", "data": encoded}),
            json.dumps({"type": "ping", "data": ""}),
        ])

        with pytest.raises(WebSocketDisconnect):
            await asyncio.wait_for(
                _forward_client_messages(websocket, scheduler),
                timeout=0.1,
            )

        await scheduler.close()
        assert websocket.sent == [{"type": "pong", "data": ""}]

    asyncio.run(scenario())


def test_rejects_additional_audio_while_submission_is_blocked():
    async def scenario():
        scheduler = InputScheduler(audio_capacity=1)
        await scheduler.submit_audio(b"queued")
        encoded = base64.b64encode(b"data").decode("ascii")
        websocket = FakeWebSocket([
            json.dumps({"type": "audio", "data": encoded}),
            json.dumps({"type": "audio", "data": encoded}),
        ])

        with pytest.raises(WebSocketDisconnect):
            await _forward_client_messages(websocket, scheduler)
        await scheduler.close()

        assert websocket.sent == [{
            "type": "error",
            "data": "音频输入处理繁忙，请稍后重试",
        }]

    asyncio.run(scenario())


def test_rejects_additional_text_while_submission_is_blocked():
    async def scenario():
        scheduler = InputScheduler(audio_capacity=1, text_capacity=1)
        await scheduler.submit_text("queued")
        websocket = FakeWebSocket([
            json.dumps({"type": "text", "data": "blocked"}),
            json.dumps({"type": "text", "data": "dropped"}),
        ])

        with pytest.raises(WebSocketDisconnect):
            await _forward_client_messages(websocket, scheduler)
        await scheduler.close()

        assert websocket.sent == [{
            "type": "error",
            "data": "文本输入处理繁忙，请稍后重试",
        }]

    asyncio.run(scenario())


def test_delayed_scheduler_send_failure_propagates_during_close():
    async def scenario():
        encoded = base64.b64encode(b"data").decode("ascii")
        send_started = asyncio.Event()
        fail_send = asyncio.Event()

        class DisconnectAfterSendStartsWebSocket(FakeWebSocket):
            async def receive_text(self):
                try:
                    return await super().receive_text()
                except WebSocketDisconnect:
                    await send_started.wait()
                    fail_send.set()
                    raise

        class FailingSession(RecordingSession):
            async def send_audio(self, data):
                send_started.set()
                await fail_send.wait()
                raise RuntimeError("delayed send failed")

        websocket = DisconnectAfterSendStartsWebSocket([
            json.dumps({"type": "audio", "data": encoded}),
        ])

        with pytest.raises(RuntimeError, match="delayed send failed"):
            await _run_session(websocket, FailingSession())

    asyncio.run(scenario())


def test_disconnect_with_saturated_queues_leaves_no_tasks(monkeypatch):
    async def scenario():
        encoded = base64.b64encode(b"data").decode("ascii")
        send_started = asyncio.Event()

        class ContinueAfterSendStartsWebSocket(FakeWebSocket):
            async def receive_text(self):
                message = await super().receive_text()
                if message != self.first_message:
                    await send_started.wait()
                return message

        class StalledSession(RecordingSession):
            async def send_text(self, data):
                self.calls.append(("text", data))
                send_started.set()
                await asyncio.Event().wait()

        websocket = ContinueAfterSendStartsWebSocket([
            json.dumps({"type": "text", "data": "stall"}),
            json.dumps({"type": "audio", "data": encoded}),
            json.dumps({"type": "audio", "data": encoded}),
            json.dumps({"type": "text", "data": "queued"}),
            json.dumps({"type": "text", "data": "blocked"}),
        ])
        websocket.first_message = json.dumps({
            "type": "text",
            "data": "stall",
        })

        monkeypatch.setattr(
            websocket_api.settings,
            "audio_queue_capacity",
            1,
        )
        monkeypatch.setattr(
            websocket_api.settings,
            "text_queue_capacity",
            1,
        )
        monkeypatch.setattr(
            websocket_api.settings,
            "scheduler_shutdown_timeout_seconds",
            0.01,
        )

        with pytest.raises(WebSocketDisconnect):
            await asyncio.wait_for(
                _run_session(websocket, StalledSession()),
                timeout=0.2,
            )

        assert send_started.is_set()
        current = asyncio.current_task()
        assert [
            task
            for task in asyncio.all_tasks()
            if task is not current and not task.done()
        ] == []

    asyncio.run(scenario())


def test_wait_for_start_supports_ping_pong_and_rejects_other_messages():
    async def scenario():
        encoded = base64.b64encode(b"data").decode("ascii")
        websocket = FakeWebSocket([
            json.dumps({"type": "ping", "data": ""}),
            json.dumps({"type": "pong", "data": ""}),
            json.dumps({"type": "audio", "data": encoded}),
            json.dumps({"type": "start_session", "data": ""}),
        ])

        await _wait_for_start(websocket)

        assert websocket.sent == [
            {"type": "pong", "data": ""},
            {"type": "error", "data": "请先发送 start_session"},
        ]

    asyncio.run(scenario())


def test_gemini_is_not_created_before_valid_start():
    async def scenario():
        created = 0

        def service_factory():
            nonlocal created
            created += 1
            raise AssertionError("service must not be created")

        websocket = FakeWebSocket([
            json.dumps({"type": "ping", "data": ""}),
        ])

        await _serve_websocket(websocket, service_factory=service_factory)

        assert websocket.accepted
        assert created == 0
        assert websocket.sent == [{"type": "pong", "data": ""}]

    asyncio.run(scenario())


def test_stop_sends_stopped_and_allows_repeated_sessions():
    async def scenario():
        services = []

        def service_factory():
            service = FakeService(RecordingSession())
            services.append(service)
            return service

        websocket = FakeWebSocket([
            json.dumps({"type": "start_session", "data": ""}),
            json.dumps({
                "type": "audio",
                "data": base64.b64encode(b"data").decode("ascii"),
            }),
            json.dumps({"type": "stop_session", "data": ""}),
            json.dumps({"type": "start_session", "data": ""}),
            json.dumps({"type": "stop_session", "data": ""}),
        ])

        await _serve_websocket(websocket, service_factory=service_factory)

        assert len(services) == 2
        assert all(service.released for service in services)
        assert [
            message
            for message in websocket.sent
            if message["type"] == "status"
        ] == [
            {"type": "status", "data": "connected"},
            {"type": "status", "data": "stopped"},
            {"type": "status", "data": "connected"},
            {"type": "status", "data": "stopped"},
        ]
        usage_events = [
            message["data"]
            for message in websocket.sent
            if message["type"] == "usage"
        ]
        assert len(usage_events) == 2
        assert usage_events[0]["audio_bytes"] == 4
        assert usage_events[1]["audio_bytes"] == 0

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("exception_type", "expected_status"),
    [
        (SessionIdleTimeout, "idle_timeout"),
        (SessionLifetimeExceeded, "max_duration"),
    ],
)
def test_runtime_expiration_sends_distinct_status(
    exception_type,
    expected_status,
):
    async def scenario():
        terminal_status_sent = asyncio.Event()

        class ExpiringRuntime:
            async def wait_until_expired(self):
                raise exception_type

            def record_activity(self):
                pass

        class DisconnectAfterStatusWebSocket(FakeWebSocket):
            async def receive_text(self):
                try:
                    return next(self.messages)
                except StopIteration:
                    await terminal_status_sent.wait()
                    raise WebSocketDisconnect()

            async def send_json(self, payload):
                await super().send_json(payload)
                if payload == {
                    "type": "status",
                    "data": expected_status,
                }:
                    terminal_status_sent.set()

        service = FakeService(RecordingSession())
        websocket = DisconnectAfterStatusWebSocket([
            json.dumps({"type": "start_session", "data": ""}),
        ])

        await _serve_websocket(
            websocket,
            service_factory=lambda: service,
            runtime_factory=ExpiringRuntime,
        )

        assert service.released
        assert websocket.sent[0:2] == [
            {"type": "status", "data": "connected"},
            {"type": "status", "data": expected_status},
        ]
        assert websocket.sent[2]["type"] == "usage"
        assert sum(
            message["type"] == "usage"
            for message in websocket.sent
        ) == 1

    asyncio.run(scenario())


def test_activity_refreshes_only_after_valid_input_is_accepted():
    async def scenario():
        submission_started = asyncio.Event()
        accept_submission = asyncio.Event()
        activity_recorded = asyncio.Event()
        allow_stop = asyncio.Event()

        class ControlledScheduler:
            async def submit_text(self, data):
                assert data == "accepted"
                submission_started.set()
                await accept_submission.wait()

        class StopControlledWebSocket(FakeWebSocket):
            async def receive_text(self):
                try:
                    return next(self.messages)
                except StopIteration:
                    await allow_stop.wait()
                    return json.dumps({
                        "type": "stop_session",
                        "data": "",
                    })

        class RecordingRuntime:
            def __init__(self):
                self.activities = 0

            def record_activity(self):
                self.activities += 1
                activity_recorded.set()

        websocket = StopControlledWebSocket([
            json.dumps({"type": "audio", "data": "%%%"}),
            json.dumps({"type": "ping", "data": ""}),
            json.dumps({"type": "text", "data": "accepted"}),
        ])
        runtime = RecordingRuntime()
        forwarding = asyncio.create_task(
            _forward_client_messages(
                websocket,
                ControlledScheduler(),
                runtime,
            )
        )

        await submission_started.wait()
        assert runtime.activities == 0

        accept_submission.set()
        await activity_recorded.wait()
        assert runtime.activities == 1

        allow_stop.set()
        assert await forwarding is SessionEndReason.STOPPED

    asyncio.run(scenario())


def test_user_stop_wins_when_timeout_completes_in_same_turn():
    async def scenario():
        class ExpiredRuntime:
            async def wait_until_expired(self):
                raise SessionIdleTimeout

            def record_activity(self):
                pass

        websocket = FakeWebSocket([
            json.dumps({"type": "stop_session", "data": ""}),
        ])

        reason = await _run_session(
            websocket,
            RecordingSession(),
            ExpiredRuntime(),
        )

        assert reason is SessionEndReason.STOPPED

    asyncio.run(scenario())


def test_natural_gemini_stream_end_sends_stopped():
    async def scenario():
        stopped = asyncio.Event()

        class NaturalEndSession(RecordingSession):
            async def receive(self):
                if False:
                    yield

        class DisconnectAfterStoppedWebSocket(FakeWebSocket):
            async def receive_text(self):
                try:
                    return next(self.messages)
                except StopIteration:
                    await stopped.wait()
                    raise WebSocketDisconnect()

            async def send_json(self, payload):
                await super().send_json(payload)
                if payload == {"type": "status", "data": "stopped"}:
                    stopped.set()

        service = FakeService(NaturalEndSession())
        websocket = DisconnectAfterStoppedWebSocket([
            json.dumps({"type": "start_session", "data": ""}),
        ])

        await _serve_websocket(
            websocket,
            service_factory=lambda: service,
        )

        assert service.released
        assert websocket.sent[0:2] == [
            {"type": "status", "data": "connected"},
            {"type": "status", "data": "stopped"},
        ]
        assert websocket.sent[2]["type"] == "usage"
        assert sum(
            message["type"] == "usage"
            for message in websocket.sent
        ) == 1

    asyncio.run(scenario())


def test_budget_end_closes_cloud_session_and_sends_one_final_usage():
    async def scenario():
        budget_status_sent = asyncio.Event()
        input_send_started = asyncio.Event()
        input_send_cancelled = asyncio.Event()

        class BudgetSession(RecordingSession):
            async def send_text(self, data):
                assert data == "accepted"
                input_send_started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    input_send_cancelled.set()
                    raise

            async def receive(self):
                await input_send_started.wait()
                yield GeminiResponse(
                    usage_metadata=types.UsageMetadata(
                        prompt_token_count=8,
                        response_token_count=2,
                        total_token_count=10,
                    )
                )

        class DisconnectAfterUsageWebSocket(FakeWebSocket):
            async def receive_text(self):
                try:
                    return next(self.messages)
                except StopIteration:
                    await budget_status_sent.wait()
                    raise WebSocketDisconnect()

            async def send_json(self, payload):
                await super().send_json(payload)
                if payload == {
                    "type": "status",
                    "data": "budget_exceeded",
                }:
                    budget_status_sent.set()

        service = FakeService(BudgetSession())
        websocket = DisconnectAfterUsageWebSocket([
            json.dumps({"type": "start_session", "data": ""}),
            json.dumps({"type": "text", "data": "accepted"}),
        ])

        await _serve_websocket(
            websocket,
            service_factory=lambda: service,
            usage_factory=lambda: SessionUsage(token_budget=10),
        )

        assert service.released
        assert input_send_cancelled.is_set()
        assert websocket.sent[0:2] == [
            {"type": "status", "data": "connected"},
            {"type": "status", "data": "budget_exceeded"},
        ]
        assert websocket.sent[2]["type"] == "usage"
        assert websocket.sent[2]["data"]["text_chars"] == 8
        assert websocket.sent[2]["data"]["total_tokens"] == 10
        assert sum(
            message["type"] == "usage"
            for message in websocket.sent
        ) == 1

    asyncio.run(scenario())


def test_cleanup_has_second_hard_timeout_and_observes_late_exception(
    monkeypatch,
    caplog,
):
    async def scenario():
        release_cancel = asyncio.Event()
        response_cancelled = asyncio.Event()

        class SlowCancelSession(RecordingSession):
            async def receive(self):
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    response_cancelled.set()
                    await release_cancel.wait()
                    raise RuntimeError("late cancellation failure")
                if False:
                    yield

        monkeypatch.setattr(
            websocket_api.settings,
            "scheduler_shutdown_timeout_seconds",
            0.01,
        )
        websocket = FakeWebSocket([
            json.dumps({"type": "stop_session", "data": ""}),
        ])

        reason = await asyncio.wait_for(
            _run_session(websocket, SlowCancelSession()),
            timeout=1,
        )

        assert reason is SessionEndReason.STOPPED
        assert response_cancelled.is_set()

        release_cancel.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert "late cancellation failure" in caplog.text

    asyncio.run(scenario())


def test_go_away_reconnects_once_with_latest_handle():
    async def scenario():
        resumed = asyncio.Event()

        class ResumeAwareWebSocket(FakeWebSocket):
            stop_sent = False

            async def receive_text(self):
                try:
                    return next(self.messages)
                except StopIteration:
                    if self.stop_sent:
                        raise WebSocketDisconnect()
                    await resumed.wait()
                    self.stop_sent = True
                    return json.dumps({
                        "type": "stop_session",
                        "data": "",
                    })

        class FirstSession(RecordingSession):
            async def receive(self):
                yield GeminiResponse(
                    payload={
                        "type": "session_resumption",
                        "data": {"resumable": True},
                    },
                    resumption_handle="latest-handle",
                    resumable=True,
                )
                yield GeminiResponse(
                    payload={
                        "type": "go_away",
                        "data": {"time_left_ms": 5000},
                    },
                    go_away=True,
                )

        class ReconnectingService:
            model = "fake-live-model"

            def __init__(self):
                self.handles = []

            @asynccontextmanager
            async def connect(self, resume_handle=None):
                self.handles.append(resume_handle)
                if resume_handle is None:
                    yield FirstSession()
                else:
                    resumed.set()
                    yield RecordingSession()

        service = ReconnectingService()
        websocket = ResumeAwareWebSocket([
            json.dumps({"type": "start_session", "data": ""}),
        ])

        await _serve_websocket(
            websocket,
            service_factory=lambda: service,
        )

        assert service.handles == [None, "latest-handle"]
        assert {
            "type": "session_resumption",
            "data": {"resumable": True},
        } in websocket.sent
        assert {
            "type": "go_away",
            "data": {"time_left_ms": 5000},
        } in websocket.sent
        assert sum(
            message["type"] == "usage"
            for message in websocket.sent
        ) == 1

    asyncio.run(scenario())


def test_failed_resume_falls_back_once_to_clean_session():
    async def scenario():
        fallback_connected = asyncio.Event()

        class FallbackAwareWebSocket(FakeWebSocket):
            stop_sent = False

            async def receive_text(self):
                try:
                    return next(self.messages)
                except StopIteration:
                    if self.stop_sent:
                        raise WebSocketDisconnect()
                    await fallback_connected.wait()
                    self.stop_sent = True
                    return json.dumps({
                        "type": "stop_session",
                        "data": "",
                    })

        class FirstSession(RecordingSession):
            async def receive(self):
                yield GeminiResponse(
                    payload={
                        "type": "session_resumption",
                        "data": {"resumable": True},
                    },
                    resumption_handle="rejected-handle",
                    resumable=True,
                )
                yield GeminiResponse(
                    payload={
                        "type": "go_away",
                        "data": {"time_left_ms": 1000},
                    },
                    go_away=True,
                )

        class FallbackService:
            model = "fake-live-model"

            def __init__(self):
                self.handles = []

            @asynccontextmanager
            async def connect(self, resume_handle=None):
                self.handles.append(resume_handle)
                if len(self.handles) == 1:
                    yield FirstSession()
                elif resume_handle is not None:
                    raise RuntimeError("resume rejected")
                else:
                    fallback_connected.set()
                    yield RecordingSession()

        service = FallbackService()
        websocket = FallbackAwareWebSocket([
            json.dumps({"type": "start_session", "data": ""}),
        ])

        await _serve_websocket(
            websocket,
            service_factory=lambda: service,
        )

        assert service.handles == [
            None,
            "rejected-handle",
            None,
        ]
        assert sum(
            message["type"] == "usage"
            for message in websocket.sent
        ) == 1

    asyncio.run(scenario())


def test_user_stop_does_not_trigger_resumption():
    async def scenario():
        stop_received = asyncio.Event()

        class StopAndGoAwayWebSocket(FakeWebSocket):
            async def receive_text(self):
                message = await super().receive_text()
                if json.loads(message)["type"] == "stop_session":
                    stop_received.set()
                return message

        class GoAwayAfterStopSession(RecordingSession):
            async def receive(self):
                await stop_received.wait()
                yield GeminiResponse(
                    payload={
                        "type": "go_away",
                        "data": {"time_left_ms": 1000},
                    },
                    resumption_handle="unused-handle",
                    resumable=True,
                    go_away=True,
                )

        class RecordingService:
            model = "fake-live-model"

            def __init__(self):
                self.handles = []

            @asynccontextmanager
            async def connect(self, resume_handle=None):
                self.handles.append(resume_handle)
                yield GoAwayAfterStopSession()

        service = RecordingService()
        websocket = StopAndGoAwayWebSocket([
            json.dumps({"type": "start_session", "data": ""}),
            json.dumps({"type": "stop_session", "data": ""}),
        ])

        await _serve_websocket(
            websocket,
            service_factory=lambda: service,
        )

        assert service.handles == [None]
        assert sum(
            message["type"] == "usage"
            for message in websocket.sent
        ) == 1

    asyncio.run(scenario())
