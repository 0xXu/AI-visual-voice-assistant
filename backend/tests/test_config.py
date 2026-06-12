import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import ConfigurationError, Settings


def test_invalid_local_env_does_not_break_test_collection(tmp_path):
    project_dir = tmp_path / "project"
    tests_dir = project_dir / "tests"
    tests_dir.mkdir(parents=True)
    shutil.copyfile(
        os.path.join(os.path.dirname(__file__), "conftest.py"),
        tests_dir / "conftest.py",
    )
    (project_dir / ".env").write_text(
        textwrap.dedent(
            """\
            MAX_AUDIO_BYTES=0
            MAX_VIDEO_BYTES=-1
            MAX_FRAME_AGE_MS=invalid
            MAX_TEXT_CHARS=0
            """
        ),
        encoding="utf-8",
    )
    (tests_dir / "test_collection.py").write_text(
        textwrap.dedent(
            """\
            from app.core.config import Settings, settings


            def test_settings_are_collectable():
                assert settings.max_audio_bytes == 8_192
                assert Settings(_env_file=None).max_video_bytes == 524_288
            """
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    for env_name in (
        "MODEL_NAME",
        "VOICE_NAME",
        "CORS_ORIGINS",
        "WEBSOCKET_KEEPALIVE_SECONDS",
        "MAX_AUDIO_BYTES",
        "MAX_VIDEO_BYTES",
        "MAX_FRAME_AGE_MS",
        "MAX_TEXT_CHARS",
        "AUDIO_QUEUE_CAPACITY",
        "TEXT_QUEUE_CAPACITY",
        "SCHEDULER_SHUTDOWN_TIMEOUT_SECONDS",
    ):
        env.pop(env_name, None)
    backend_dir = os.path.dirname(os.path.dirname(__file__))
    env["PYTHONPATH"] = os.pathsep.join(
        path
        for path in (backend_dir, env.get("PYTHONPATH"))
        if path
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            str(tests_dir / "test_collection.py"),
        ],
        cwd=project_dir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_defaults_to_current_live_model(monkeypatch):
    monkeypatch.delenv("MODEL_NAME", raising=False)

    settings = Settings(gemini_api_key="test-key", _env_file=None)

    assert settings.model_name == "gemini-3.1-flash-live-preview"


def test_defaults_to_safe_realtime_media_limits(monkeypatch):
    for env_name in (
        "MAX_AUDIO_BYTES",
        "MAX_VIDEO_BYTES",
        "MAX_FRAME_AGE_MS",
        "MAX_TEXT_CHARS",
        "AUDIO_QUEUE_CAPACITY",
        "TEXT_QUEUE_CAPACITY",
        "SCHEDULER_SHUTDOWN_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(env_name, raising=False)

    settings = Settings(gemini_api_key="test-key", _env_file=None)

    assert settings.max_audio_bytes == 8_192
    assert settings.max_video_bytes == 524_288
    assert settings.max_frame_age_ms == 2_000
    assert settings.max_text_chars == 2_000
    assert settings.audio_queue_capacity == 32
    assert settings.text_queue_capacity == 8
    assert settings.scheduler_shutdown_timeout_seconds == 1.0


def test_parses_scheduler_queue_and_shutdown_environment(monkeypatch):
    monkeypatch.setenv("TEXT_QUEUE_CAPACITY", "3")
    monkeypatch.setenv("SCHEDULER_SHUTDOWN_TIMEOUT_SECONDS", "0.25")

    settings = Settings(gemini_api_key="test-key", _env_file=None)

    assert settings.text_queue_capacity == 3
    assert settings.scheduler_shutdown_timeout_seconds == 0.25


def test_env_example_documents_scheduler_limits():
    env_example = (
        Path(__file__).parents[1] / ".env.example"
    ).read_text(encoding="utf-8")

    assert "TEXT_QUEUE_CAPACITY=8" in env_example
    assert "SCHEDULER_SHUTDOWN_TIMEOUT_SECONDS=1.0" in env_example


@pytest.mark.parametrize(
    "env_name",
    [
        "MAX_AUDIO_BYTES",
        "MAX_VIDEO_BYTES",
        "MAX_FRAME_AGE_MS",
        "MAX_TEXT_CHARS",
        "AUDIO_QUEUE_CAPACITY",
        "TEXT_QUEUE_CAPACITY",
        "SCHEDULER_SHUTDOWN_TIMEOUT_SECONDS",
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
        Settings(gemini_api_key="test-key", _env_file=None)


def test_requires_ai_studio_api_key():
    settings = Settings(gemini_api_key=None, _env_file=None)

    with pytest.raises(ConfigurationError, match="GEMINI_API_KEY"):
        settings.validate_authentication()


def test_parses_comma_separated_cors_origins():
    settings = Settings(
        gemini_api_key="test-key",
        cors_origins="http://localhost:3000, https://example.com",
        _env_file=None,
    )

    assert settings.allowed_origins == [
        "http://localhost:3000",
        "https://example.com",
    ]
