import asyncio
from contextlib import asynccontextmanager

from google.genai import types

from app.core.config import Settings
from app.services import gemini_service
from app.services.gemini_service import (
    GeminiResponse,
    GeminiLiveService,
    GeminiSession,
    SYSTEM_PROMPT,
    build_live_config,
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
    service = GeminiLiveService(
        Settings(gemini_api_key="test-key", _env_file=None)
    )

    service._create_client()

    assert captured == {"api_key": "test-key"}


def test_build_live_config_uses_cost_safe_live_defaults():
    app_settings = Settings(
        gemini_api_key="test-key",
        voice_name="Kore",
        _env_file=None,
    )

    config = build_live_config(app_settings)

    assert config.response_modalities == [types.Modality.AUDIO]
    assert config.media_resolution == types.MediaResolution.MEDIA_RESOLUTION_LOW
    assert config.context_window_compression is not None
    assert config.context_window_compression.sliding_window is not None
    assert (
        config.speech_config.voice_config.prebuilt_voice_config.voice_name
        == "Kore"
    )
    assert config.system_instruction == SYSTEM_PROMPT


def test_connect_uses_live_config_builder(monkeypatch):
    expected_config = object()
    captured = {}

    class FakeLive:
        @asynccontextmanager
        async def connect(self, **kwargs):
            captured.update(kwargs)
            yield object()

    class FakeAio:
        def __init__(self):
            self.live = FakeLive()

        async def aclose(self):
            captured["closed"] = True

    class FakeClient:
        def __init__(self):
            self.aio = FakeAio()

    monkeypatch.setattr(
        gemini_service,
        "build_live_config",
        lambda app_settings: expected_config,
    )
    service = GeminiLiveService(
        Settings(gemini_api_key="test-key", _env_file=None)
    )
    monkeypatch.setattr(service, "_create_client", FakeClient)

    async def connect_once():
        async with service.connect() as session:
            assert isinstance(session, GeminiSession)

    asyncio.run(connect_once())

    assert captured["model"] == service.model
    assert captured["config"] is expected_config
    assert captured["closed"] is True


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


def test_maps_live_server_usage_metadata_with_sdk_type():
    metadata = types.UsageMetadata(
        prompt_token_count=12,
        response_token_count=3,
        total_token_count=15,
    )

    class ReceivingSession:
        async def receive(self):
            yield types.LiveServerMessage(usage_metadata=metadata)

    async def collect():
        return [
            event
            async for event in GeminiSession(ReceivingSession()).receive()
        ]

    assert asyncio.run(collect()) == [
        GeminiResponse(usage_metadata=metadata)
    ]
