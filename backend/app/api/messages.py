import base64
import binascii
import json
from dataclasses import dataclass
from typing import Literal

from app.core.config import Settings


MessageType = Literal["ping", "pong", "audio", "video_frame", "text"]


class ClientMessageError(ValueError):
    """客户端消息格式不符合协议。"""


@dataclass(frozen=True, slots=True)
class ClientMessage:
    type: MessageType
    data: bytes | str | None = None


def parse_client_message(raw_message: str, settings: Settings) -> ClientMessage:
    try:
        payload = json.loads(raw_message)
    except json.JSONDecodeError as exc:
        raise ClientMessageError("消息不是有效的 JSON") from exc

    if not isinstance(payload, dict):
        raise ClientMessageError("消息必须是 JSON 对象")

    message_type = payload.get("type")
    if message_type in {"ping", "pong"}:
        return ClientMessage(type=message_type)

    if message_type == "text":
        return ClientMessage(
            type="text",
            data=_parse_text(payload.get("data"), settings.max_text_chars),
        )

    if message_type == "audio":
        return ClientMessage(
            type="audio",
            data=_parse_base64(payload.get("data"), settings.max_audio_bytes),
        )

    if message_type == "video_frame":
        return ClientMessage(
            type="video_frame",
            data=_parse_base64(payload.get("data"), settings.max_video_bytes),
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

    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ClientMessageError("媒体内容不是有效的 Base64 数据") from exc

    if len(decoded) > max_bytes:
        raise ClientMessageError(f"媒体内容过大，最多允许 {max_bytes} 字节")
    return decoded
