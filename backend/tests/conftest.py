import os


_TEST_SETTINGS_DEFAULTS = {
    "MODEL_NAME": "gemini-3.1-flash-live-preview",
    "VOICE_NAME": "Aoede",
    "CORS_ORIGINS": "http://localhost:3000",
    "WEBSOCKET_KEEPALIVE_SECONDS": "20.0",
    "MAX_AUDIO_BYTES": "8192",
    "MAX_VIDEO_BYTES": "524288",
    "MAX_FRAME_AGE_MS": "2000",
    "MAX_TEXT_CHARS": "2000",
    "SESSION_IDLE_SECONDS": "45.0",
    "SESSION_MAX_SECONDS": "600.0",
}

for env_name, value in _TEST_SETTINGS_DEFAULTS.items():
    os.environ.setdefault(env_name, value)
