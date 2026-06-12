import asyncio
import base64
import json

import pytest
from fastapi import WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.api import messages
from app.api.websocket import _forward_client_messages
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
