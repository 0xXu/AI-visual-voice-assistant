import asyncio
import base64
import json

import pytest
from fastapi import WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.api import messages
from app.api.websocket import _forward_client_messages


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


class FakeGeminiSession:
    def __init__(self):
        self.audio = []
        self.video = []
        self.text = []

    async def send_audio(self, data):
        self.audio.append(data)

    async def send_video_frame(self, data):
        self.video.append(data)

    async def send_text(self, data):
        self.text.append(data)


def run_forwarder(websocket, session):
    with pytest.raises(WebSocketDisconnect):
        asyncio.run(_forward_client_messages(websocket, session))


def test_forwards_ping_and_multimodal_messages(monkeypatch):
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
    session = FakeGeminiSession()

    run_forwarder(websocket, session)

    assert websocket.sent == [{"type": "pong", "data": ""}]
    assert session.audio == [b"data"]
    assert session.video == [jpeg]
    assert session.text == ["请描述画面"]


def test_returns_chinese_error_and_continues_after_invalid_message():
    websocket = FakeWebSocket([
        json.dumps({"type": "audio", "data": "%%%"}),
        json.dumps({"type": "text", "data": "继续"}),
    ])
    session = FakeGeminiSession()

    run_forwarder(websocket, session)

    assert websocket.sent == [{
        "type": "error",
        "data": "媒体内容不是有效的 Base64 数据",
    }]
    assert session.text == ["继续"]


def test_continues_after_json_parser_value_error():
    websocket = FakeWebSocket([
        '{"type":' + "9" * 5_000 + "}",
        json.dumps({"type": "text", "data": "继续"}),
    ])
    session = FakeGeminiSession()

    run_forwarder(websocket, session)

    assert websocket.sent == [{
        "type": "error",
        "data": "消息不是有效的 JSON",
    }]
    assert session.text == ["继续"]
