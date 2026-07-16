from __future__ import annotations

from dataclasses import replace

import pytest

from study_space_hardware.config import config_from_dict, load_config


def test_example_config_loads() -> None:
    config = load_config("config/example.yaml")
    assert config.room_id == "room_a"
    assert config.window_seconds == 5
    assert config.sensors["thermal"].sample_rate_hz == 2
    assert config.actuation.buzzer_enabled is False


def test_real_example_config_loads_with_simulator_disabled() -> None:
    config = load_config("config/real.example.yaml")
    assert config.simulator.enabled is False
    assert config.sensors["radar"].options["baud_rate"] == 256000


def test_environment_variable_expansion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RADAR_PORT", "/dev/test-radar")
    config = config_from_dict(
        {
            "room_id": "room_a",
            "device_id": "pi5-a",
            "sensors": {
                "radar": {
                    "options": {"port": "${RADAR_PORT}"}
                }
            },
        }
    )
    assert config.sensors["radar"].options["port"] == "/dev/test-radar"


def test_window_duration_is_constrained() -> None:
    config = config_from_dict(
        {"room_id": "room_a", "device_id": "pi5-a"}
    )
    with pytest.raises(ValueError, match="between 5 and 10"):
        replace(config, window_seconds=4).validate()


def test_buzzer_cannot_be_enabled_in_committed_default_config() -> None:
    with pytest.raises(ValueError, match="buzzer_enabled"):
        config_from_dict(
            {
                "room_id": "room_a",
                "device_id": "pi5-a",
                "actuation": {"buzzer_enabled": True},
            }
        )
