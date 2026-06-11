import pytest

from app.core.config import ConfigurationError, Settings


def test_defaults_to_current_live_model():
    settings = Settings(gemini_api_key="test-key")

    assert settings.model_name == "gemini-3.1-flash-live-preview"


def test_defaults_to_safe_realtime_media_limits():
    settings = Settings(gemini_api_key="test-key")

    assert settings.max_audio_bytes == 8_192
    assert settings.max_video_bytes == 524_288
    assert settings.max_frame_age_ms == 2_000


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
