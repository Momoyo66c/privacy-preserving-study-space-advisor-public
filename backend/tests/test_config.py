from __future__ import annotations

from study_space_api.config import Settings


def test_cors_origins_environment_is_json_list(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:5173","https://demo.example"]')
    settings = Settings(_env_file=None)
    assert settings.cors_origins == ["http://localhost:5173", "https://demo.example"]
