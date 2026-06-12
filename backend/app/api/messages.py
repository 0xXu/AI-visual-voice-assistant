import base64
import binascii
import json
import time
from dataclasses import dataclass
from typing import Literal

from app.core.config import Settings


MessageType = Literal[
    "ping",
    "pong",
    "start_session",
    "stop_session",
    "audio",
    "video_frame",
    "text",
]


class ClientMessageError(ValueError):
    """客户端消息格式不符合协议。"""


@dataclass(frozen=True, slots=True)
class ClientMessage:
    type: MessageType
    data: bytes | str | None = None
    timestamp_ms: int | None = None
    sequence: int | None = None


def parse_client_message(
    raw_message: str,
    settings: Settings,
    *,
    now_ms: int | None = None,
) -> ClientMessage:
    try:
        payload = json.loads(raw_message)
    except json.JSONDecodeError as exc:
        raise ClientMessageError("消息不是有效的 JSON") from exc

    if not isinstance(payload, dict):
        raise ClientMessageError("消息必须是 JSON 对象")

    message_type = payload.get("type")
    if message_type in {"ping", "pong", "start_session", "stop_session"}:
        return ClientMessage(type=message_type)

    if message_type == "text":
        return ClientMessage(
            type="text",
            data=_parse_text(payload.get("data"), settings.max_text_chars),
        )

    if message_type == "audio":
        return ClientMessage(
            type="audio",
            data=_parse_audio(payload.get("data"), settings.max_audio_bytes),
        )

    if message_type == "video_frame":
        return _parse_video_frame(
            payload,
            settings,
            now_ms=time.time_ns() // 1_000_000 if now_ms is None else now_ms,
        )

    raise ClientMessageError(f"不支持的消息类型：{message_type!r}")


def _parse_text(value: object, max_chars: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ClientMessageError("文本内容不能为空")
    if len(value) > max_chars:
        raise ClientMessageError(f"文本内容过长，最多允许 {max_chars} 个字符")
    return value.strip()


def _parse_base64(value: object, max_bytes: int) -> bytes:
    if not isinstance(value, str) or not value:
        raise ClientMessageError("媒体内容不能为空")
    if len(value) > 4 * ((max_bytes + 2) // 3):
        raise ClientMessageError(f"媒体内容过大，最多允许 {max_bytes} 字节")

    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ClientMessageError("媒体内容不是有效的 Base64 数据") from exc

    if len(decoded) > max_bytes:
        raise ClientMessageError(f"媒体内容过大，最多允许 {max_bytes} 字节")
    return decoded


def _parse_audio(value: object, max_bytes: int) -> bytes:
    decoded = _parse_base64(value, max_bytes)
    if len(decoded) % 2:
        raise ClientMessageError("PCM16 音频必须包含偶数字节")
    return decoded


def _parse_video_frame(
    payload: dict[str, object],
    settings: Settings,
    *,
    now_ms: int,
) -> ClientMessage:
    decoded = _parse_base64(payload.get("data"), settings.max_video_bytes)
    if not decoded.startswith(b"\xff\xd8") or not decoded.endswith(b"\xff\xd9"):
        raise ClientMessageError("视频帧必须是有效的 JPEG 数据")

    timestamp_ms = _parse_integer(payload.get("timestamp"), "timestamp")
    sequence = _parse_integer(payload.get("sequence"), "sequence")
    age_ms = now_ms - timestamp_ms
    if age_ms > settings.max_frame_age_ms:
        raise ClientMessageError("视频帧已过期")
    if age_ms < -settings.max_frame_age_ms:
        raise ClientMessageError("视频帧时间戳过于超前")

    return ClientMessage(
        type="video_frame",
        data=decoded,
        timestamp_ms=timestamp_ms,
        sequence=sequence,
    )


def _parse_integer(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise ClientMessageError(f"{field_name} 必须是整数")
    return value
