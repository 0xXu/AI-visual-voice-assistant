import asyncio

from app.core.config import Settings
from app.services import gemini_service
from app.services.gemini_service import (
    GeminiLiveService,
    GeminiSession,
    SYSTEM_PROMPT,
)


class FakeSession:
    def __init__(self):
        self.calls = []

    async def send_realtime_input(self, **kwargs):
        self.calls.append(kwargs)


def test_prompt_defines_visual_conversation_behavior():
    required_phrases = [
        "优先回答用户当前的问题",
        "无法确认",
        "即时危险",
        "不要猜测人物身份",
        "跟随用户使用的语言",
        "简短、自然",
    ]

    for phrase in required_phrases:
        assert phrase in SYSTEM_PROMPT


def test_creates_ai_studio_client_with_api_key(monkeypatch):
    captured = {}

    def fake_client(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(gemini_service.genai, "Client", fake_client)
    service = GeminiLiveService(Settings(gemini_api_key="test-key"))

    service._create_client()

    assert captured == {"api_key": "test-key"}


def test_sends_audio_with_explicit_sample_rate():
    fake_session = FakeSession()
    session = GeminiSession(fake_session)

    asyncio.run(session.send_audio(b"pcm"))

    audio = fake_session.calls[0]["audio"]
    assert audio.data == b"pcm"
    assert audio.mime_type == "audio/pcm;rate=16000"


def test_sends_video_and_text_as_realtime_input():
    fake_session = FakeSession()
    session = GeminiSession(fake_session)

    asyncio.run(session.send_video_frame(b"jpeg"))
    asyncio.run(session.send_text("你好"))

    assert fake_session.calls[0]["video"].mime_type == "image/jpeg"
    assert fake_session.calls[1] == {"text": "你好"}
