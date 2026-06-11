from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigurationError(RuntimeError):
    """应用配置不完整或互相冲突。"""


class Settings(BaseSettings):
    gemini_api_key: SecretStr | None = None
    model_name: str = "gemini-3.1-flash-live-preview"
    voice_name: str = "Aoede"

    cors_origins: str = "http://localhost:3000"
    websocket_keepalive_seconds: float = 20.0
    max_audio_bytes: int = 256 * 1024
    max_video_bytes: int = 2 * 1024 * 1024
    max_text_chars: int = 2_000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=("settings_",),
    )

    @property
    def allowed_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]

    def validate_authentication(self) -> None:
        if self.gemini_api_key is None:
            raise ConfigurationError(
                "使用 Google AI Studio 时必须设置 GEMINI_API_KEY"
            )


settings = Settings()
