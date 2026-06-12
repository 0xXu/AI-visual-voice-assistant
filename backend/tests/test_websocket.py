import asyncio
import base64
import json

import pytest
from fastapi import WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.api import messages, websocket as websocket_api
from app.api.websocket import _forward_client_messages, _run_session
from app.services.input_scheduler import InputScheduler


class FakeWebSocket:
    client_state = WebSocketState.CONNECTED

    def __init__(self, messages):
        self.messages = iter(messages)
        self.sent = []

    async def receive_text(self):
        try:
            return next(self.messages)
        except StopIteration as exc:
            raise WebSocketDisconnect() from exc

    async def send_json(self, payload):
        self.sent.append(payload)


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
