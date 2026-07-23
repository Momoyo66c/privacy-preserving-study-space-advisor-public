from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./study_space.db"
    stale_after_seconds: int = Field(default=30, ge=1)
    expected_observation_interval_seconds: int = Field(default=5, ge=1)
    max_request_body_bytes: int = Field(default=131_072, ge=8_192)
    max_history_hours: int = Field(default=168, ge=1, le=744)
    max_history_points: int = Field(default=2_000, ge=1, le=10_000)
    future_skew_seconds: int = Field(default=300, ge=0)
    delayed_observation_warning_seconds: int = Field(default=86_400, ge=0)
    max_observation_age_days: int = Field(default=30, ge=1)
    observation_retention_days: int = Field(default=30, ge=1)
    forecast_retention_days: int = Field(default=30, ge=1)
    recommendation_retention_days: int = Field(default=7, ge=1)
    auto_register_devices: bool = True
    edge_api_token: str | None = None
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    recommendation_adapter_timeout_seconds: float = Field(default=2.0, gt=0, le=30)
    allow_anonymous_demo: bool = True
    session_ttl_seconds: int = Field(default=28_800, ge=300, le=604_800)
    session_cookie_secure: bool = False
    login_max_failures: int = Field(default=5, ge=1, le=100)
    login_failure_window_seconds: int = Field(default=900, ge=60, le=86_400)
    selection_retention_days: int = Field(default=90, ge=1, le=3650)

    @field_validator("edge_api_token", mode="before")
    @classmethod
    def empty_token_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @model_validator(mode="after")
    def production_security_defaults(self) -> "Settings":
        if self.app_env == "production":
            self.allow_anonymous_demo = False
            self.session_cookie_secure = True
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
