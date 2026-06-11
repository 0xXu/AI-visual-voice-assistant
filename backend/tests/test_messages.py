import base64
import json

import pytest

from app.api.messages import ClientMessageError, parse_client_message
from app.core.config import Settings


@pytest.fixture
def settings():
    return Settings(
        gemini_api_key="test-key",
        max_audio_bytes=8,
        max_video_bytes=16,
        max_text_chars=10,
    )


def encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def test_parses_audio_bytes(settings):
    message = parse_client_message(
        json.dumps({"type": "audio", "data": encode(b"audio")}),
        settings,
    )

    assert message.type == "audio"
    assert message.data == b"audio"


def test_rejects_invalid_base64(settings):
    with pytest.raises(ClientMessageError, match="Base64"):
        parse_client_message(
            json.dumps({"type": "video_frame", "data": "%%%"}),
            settings,
        )


def test_rejects_oversized_binary_payload(settings):
    with pytest.raises(ClientMessageError, match="过大"):
        parse_client_message(
            json.dumps({"type": "audio", "data": encode(b"123456789")}),
            settings,
        )


def test_rejects_blank_or_oversized_text(settings):
    with pytest.raises(ClientMessageError, match="不能为空"):
        parse_client_message(json.dumps({"type": "text", "data": "  "}), settings)

    with pytest.raises(ClientMessageError, match="过长"):
        parse_client_message(
            json.dumps({"type": "text", "data": "12345678901"}),
            settings,
        )


def test_rejects_unknown_message_type(settings):
    with pytest.raises(ClientMessageError, match="不支持"):
        parse_client_message(json.dumps({"type": "unknown", "data": ""}), settings)
