import pytest
from pydantic import ValidationError

from app.core.config import ConfigurationError, Settings


def test_defaults_to_current_live_model(monkeypatch):
    monkeypatch.delenv("MODEL_NAME", raising=False)

    settings = Settings(gemini_api_key="test-key")

    assert settings.model_name == "gemini-3.1-flash-live-preview"


def test_defaults_to_safe_realtime_media_limits(monkeypatch):
    for env_name in (
        "MAX_AUDIO_BYTES",
        "MAX_VIDEO_BYTES",
        "MAX_FRAME_AGE_MS",
        "MAX_TEXT_CHARS",
    ):
        monkeypatch.delenv(env_name, raising=False)

    settings = Settings(gemini_api_key="test-key")

    assert settings.max_audio_bytes == 8_192
    assert settings.max_video_bytes == 524_288
    assert settings.max_frame_age_ms == 2_000
    assert settings.max_text_chars == 2_000


@pytest.mark.parametrize(
    "env_name",
    [
        "MAX_AUDIO_BYTES",
        "MAX_VIDEO_BYTES",
        "MAX_FRAME_AGE_MS",
        "MAX_TEXT_CHARS",
    ],
)
@pytest.mark.parametrize("value", [0, -1])
def test_rejects_non_positive_realtime_media_limits_from_environment(
    monkeypatch,
    env_name,
    value,
):
    monkeypatch.setenv(env_name, str(value))

    with pytest.raises(ValidationError):
        Settings(gemini_api_key="test-key")


def test_requires_ai_studio_api_key():
    settings = Settings(gemini_api_key=None)

    with pytest.raises(ConfigurationError, match="GEMINI_API_KEY"):
        settings.validate_authentication()


def test_parses_comma_separated_cors_origins():
    settings = Settings(
        gemini_api_key="test-key",
        cors_origins="http://localhost:3000, https://example.com",
    )

    assert settings.allowed_origins == [
        "http://localhost:3000",
        "https://example.com",
    ]
