import base64
import json

import pytest

from app.api import messages
from app.api.messages import ClientMessageError, parse_client_message
from app.core.config import Settings


@pytest.fixture
def settings():
    return Settings(
        gemini_api_key="test-key",
        max_audio_bytes=8,
        max_video_bytes=16,
        max_frame_age_ms=2_000,
        max_text_chars=10,
    )


def encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def test_parses_audio_bytes(settings):
    message = parse_client_message(
        json.dumps({"type": "audio", "data": encode(b"\x01\x02")}),
        settings,
    )

    assert message.type == "audio"
    assert message.data == b"\x01\x02"


def test_allows_even_audio_at_max_bytes(settings):
    audio = b"\x01\x02" * (settings.max_audio_bytes // 2)

    message = parse_client_message(
        json.dumps({"type": "audio", "data": encode(audio)}),
        settings,
    )

    assert message.data == audio


@pytest.mark.parametrize("message_type", ["start_session", "stop_session"])
def test_rejects_unreleased_lifecycle_messages(settings, message_type):
    with pytest.raises(ClientMessageError, match="不支持"):
        parse_client_message(json.dumps({"type": message_type}), settings)


def test_rejects_odd_length_pcm16_audio(settings):
    with pytest.raises(ClientMessageError, match="PCM16"):
        parse_client_message(
            json.dumps({"type": "audio", "data": encode(b"\x01")}),
            settings,
        )


def test_rejects_invalid_base64(settings):
    with pytest.raises(ClientMessageError, match="Base64"):
        parse_client_message(
            json.dumps(
                {
                    "type": "video_frame",
                    "data": "%%%",
                    "timestamp": 1_000,
                    "sequence": 1,
                }
            ),
            settings,
            now_ms=1_000,
        )


def test_rejects_oversized_binary_payload(settings):
    with pytest.raises(ClientMessageError, match="过大"):
        parse_client_message(
            json.dumps({"type": "audio", "data": encode(b"1234567890")}),
            settings,
        )


def test_rejects_oversized_base64_before_decoding(settings, monkeypatch):
    def fail_if_called(*args, **kwargs):
        pytest.fail("oversized Base64 payload must not be decoded")

    monkeypatch.setattr(messages.base64, "b64decode", fail_if_called)

    with pytest.raises(ClientMessageError, match="过大"):
        parse_client_message(
            json.dumps({"type": "audio", "data": "A" * 16}),
            settings,
        )


def test_parses_jpeg_video_with_timestamp_and_sequence(settings):
    jpeg = b"\xff\xd8frame\xff\xd9"

    message = parse_client_message(
        json.dumps(
            {
                "type": "video_frame",
                "data": encode(jpeg),
                "timestamp": 9_000,
                "sequence": 7,
            }
        ),
        settings,
        now_ms=10_000,
    )

    assert message.type == "video_frame"
    assert message.data == jpeg
    assert message.timestamp_ms == 9_000
    assert message.sequence == 7


def test_allows_jpeg_video_at_max_bytes(settings):
    jpeg = b"\xff\xd8" + b"\x00" * (settings.max_video_bytes - 4) + b"\xff\xd9"

    message = parse_client_message(
        json.dumps(
            {
                "type": "video_frame",
                "data": encode(jpeg),
                "timestamp": 1_000,
                "sequence": 1,
            }
        ),
        settings,
        now_ms=1_000,
    )

    assert message.data == jpeg


def test_rejects_jpeg_video_one_byte_over_max(settings):
    jpeg = b"\xff\xd8" + b"\x00" * (settings.max_video_bytes - 3) + b"\xff\xd9"

    with pytest.raises(ClientMessageError, match="过大"):
        parse_client_message(
            json.dumps(
                {
                    "type": "video_frame",
                    "data": encode(jpeg),
                    "timestamp": 1_000,
                    "sequence": 1,
                }
            ),
            settings,
            now_ms=1_000,
        )


def test_rejects_non_jpeg_video(settings):
    with pytest.raises(ClientMessageError, match="JPEG"):
        parse_client_message(
            json.dumps(
                {
                    "type": "video_frame",
                    "data": encode(b"not-a-jpeg"),
                    "timestamp": 1_000,
                    "sequence": 1,
                }
            ),
            settings,
            now_ms=1_000,
        )


@pytest.mark.parametrize("field", ["timestamp", "sequence"])
def test_rejects_video_without_integer_metadata(settings, field):
    payload = {
        "type": "video_frame",
        "data": encode(b"\xff\xd8frame\xff\xd9"),
        "timestamp": 1_000,
        "sequence": 1,
    }
    payload[field] = "invalid"

    with pytest.raises(ClientMessageError, match=field):
        parse_client_message(json.dumps(payload), settings, now_ms=1_000)


def test_rejects_stale_video_frame(settings):
    with pytest.raises(ClientMessageError, match="过期"):
        parse_client_message(
            json.dumps(
                {
                    "type": "video_frame",
                    "data": encode(b"\xff\xd8frame\xff\xd9"),
                    "timestamp": 7_999,
                    "sequence": 1,
                }
            ),
            settings,
            now_ms=10_000,
        )


def test_allows_video_frame_at_past_clock_skew_boundary(settings):
    message = parse_client_message(
        json.dumps(
            {
                "type": "video_frame",
                "data": encode(b"\xff\xd8frame\xff\xd9"),
                "timestamp": 8_000,
                "sequence": 1,
            }
        ),
        settings,
        now_ms=10_000,
    )

    assert message.timestamp_ms == 8_000


def test_rejects_video_frame_beyond_future_clock_skew(settings):
    with pytest.raises(ClientMessageError, match="时间戳.*超前"):
        parse_client_message(
            json.dumps(
                {
                    "type": "video_frame",
                    "data": encode(b"\xff\xd8frame\xff\xd9"),
                    "timestamp": 12_001,
                    "sequence": 1,
                }
            ),
            settings,
            now_ms=10_000,
        )


def test_allows_video_frame_at_future_clock_skew_boundary(settings):
    message = parse_client_message(
        json.dumps(
            {
                "type": "video_frame",
                "data": encode(b"\xff\xd8frame\xff\xd9"),
                "timestamp": 12_000,
                "sequence": 1,
            }
        ),
        settings,
        now_ms=10_000,
    )

    assert message.timestamp_ms == 12_000


def test_uses_current_time_for_video_expiration(settings, monkeypatch):
    monkeypatch.setattr(messages.time, "time_ns", lambda: 10_000_000_000)

    with pytest.raises(ClientMessageError, match="过期"):
        parse_client_message(
            json.dumps(
                {
                    "type": "video_frame",
                    "data": encode(b"\xff\xd8frame\xff\xd9"),
                    "timestamp": 7_999,
                    "sequence": 1,
                }
            ),
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


def test_allows_text_at_max_chars(settings):
    text = "x" * settings.max_text_chars

    message = parse_client_message(
        json.dumps({"type": "text", "data": text}),
        settings,
    )

    assert message.data == text


def test_rejects_unknown_message_type(settings):
    with pytest.raises(ClientMessageError, match="不支持"):
        parse_client_message(json.dumps({"type": "unknown", "data": ""}), settings)
