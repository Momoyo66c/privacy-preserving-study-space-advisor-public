from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tomllib

import pytest

from study_space_hardware.config import config_from_dict, load_config


PROJECT_ROOT = Path(__file__).parents[1]
EXAMPLE_CONFIG = PROJECT_ROOT / "config/example.yaml"
REAL_CONFIG = PROJECT_ROOT / "config/real.example.yaml"


def test_example_config_loads() -> None:
    config = load_config(EXAMPLE_CONFIG)
    assert config.room_id == "room_a"
    assert config.window_seconds == 5
    assert config.sensors["thermal"].sample_rate_hz == 2
    assert config.actuation.buzzer_enabled is False


def test_real_example_config_loads_with_explicit_radar_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RADAR_PORT", "/dev/serial/by-id/ld2450-test")
    config = load_config(REAL_CONFIG)
    assert config.simulator.enabled is False
    assert config.sensors["radar"].options["port"] == (
        "/dev/serial/by-id/ld2450-test"
    )
    assert config.sensors["radar"].options["baud_rate"] == 256000


def test_real_example_config_rejects_missing_radar_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RADAR_PORT", raising=False)
    with pytest.raises(ValueError, match="missing environment variable: RADAR_PORT"):
        load_config(REAL_CONFIG)


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


def test_hardware_extra_includes_pi5_gpio_backend() -> None:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as file:
        project = tomllib.load(file)["project"]

    hardware_dependencies = project["optional-dependencies"]["hardware"]
    assert any(
        dependency.startswith("lgpio>=")
        and "platform_machine == 'aarch64'" in dependency
        for dependency in hardware_dependencies
    )
