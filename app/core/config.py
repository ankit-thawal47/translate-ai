from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    database_url: str = Field(
        default="postgresql+psycopg://bridgeai:bridgeai@localhost:5432/bridgeai",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    minio_endpoint: str = Field(default="http://localhost:9000", alias="MINIO_ENDPOINT")
    minio_access_key: str = Field(default="minioadmin", alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(default="minioadmin", alias="MINIO_SECRET_KEY")
    minio_bucket: str = Field(default="bridgeai-audio", alias="MINIO_BUCKET")
    tmp_dir: Path = Field(default=Path("./tmp"), alias="TMP_DIR")
    log_dir: Path = Field(default=Path("./logs"), alias="LOG_DIR")
    stt_window_seconds: int = Field(default=5, alias="STT_WINDOW_SECONDS")
    ingress_queue_cap: int = Field(default=10, alias="INGRESS_QUEUE_CAP")
    max_session_duration_seconds: int = Field(default=240, alias="MAX_SESSION_DURATION_SECONDS")
    cors_origins: str = Field(default="http://localhost:5173", alias="CORS_ORIGINS")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.tmp_dir.mkdir(parents=True, exist_ok=True)
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    return settings

