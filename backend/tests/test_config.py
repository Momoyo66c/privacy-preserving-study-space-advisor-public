from __future__ import annotations

from study_space_api.config import Settings


def test_cors_origins_environment_is_json_list(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:5173","https://demo.example"]')
    settings = Settings(_env_file=None)
    assert settings.cors_origins == ["http://localhost:5173", "https://demo.example"]


def test_production_forces_secure_sessions_and_disables_anonymous_demo() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        allow_anonymous_demo=True,
        session_cookie_secure=False,
    )
    assert settings.allow_anonymous_demo is False
    assert settings.session_cookie_secure is True
