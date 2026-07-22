from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tomllib

import pytest

from study_space_hardware.config import config_from_dict, load_config


PROJECT_ROOT = Path(__file__).parents[1]
EXAMPLE_CONFIG = PROJECT_ROOT / "config/example.yaml"
REAL_CONFIG = PROJECT_ROOT / "config/real.example.yaml"
ESP32_HUB_CONFIG = PROJECT_ROOT / "config/esp32-hub.example.yaml"


def test_example_config_loads() -> None:
    config = load_config(EXAMPLE_CONFIG)
    assert config.room_id == "room_a"
    assert config.window_seconds == 5
    assert config.sensors["thermal"].sample_rate_hz == 2
    assert config.actuation.buzzer_enabled is False
    assert config.transport.mode == "direct"


def test_real_example_disables_retired_radar_without_a_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RADAR_PORT", raising=False)
    config = load_config(REAL_CONFIG)
    assert config.simulator.enabled is False
    assert config.sensors["radar"].enabled is False
    assert config.sensors["radar"].options == {}


def test_esp32_hub_example_uses_one_explicit_serial_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "ESP32_HUB_PORT",
        "/dev/serial/by-id/usb-esp32-test",
    )
    config = load_config(ESP32_HUB_CONFIG)
    assert config.simulator.enabled is False
    assert config.transport.mode == "esp32_hub"
    assert config.transport.port == "/dev/serial/by-id/usb-esp32-test"
    assert config.transport.baud_rate == 460800
    assert "port" not in config.sensors["radar"].options
    assert config.sensors["radar"].enabled is False
    assert config.sensors["climate"].sample_rate_hz == 0.5


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


def test_esp32_hub_transport_requires_a_port() -> None:
    with pytest.raises(ValueError, match="transport.port is required"):
        config_from_dict(
            {
                "room_id": "room_a",
                "device_id": "pi5-a",
                "transport": {"mode": "esp32_hub"},
            }
        )


def test_esp32_hub_transport_loads_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ESP32_HUB_PORT", "/dev/serial/by-id/esp32-test")
    config = config_from_dict(
        {
            "room_id": "room_a",
            "device_id": "pi5-a",
            "transport": {
                "mode": "esp32_hub",
                "port": "${ESP32_HUB_PORT}",
                "baud_rate": 460800,
            },
        }
    )
    assert config.transport.port == "/dev/serial/by-id/esp32-test"
    assert config.transport.baud_rate == 460800


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("mode", "unknown", "transport.mode"),
        ("baud_rate", 0, "baud_rate"),
        ("read_timeout_s", 0, "read_timeout_s"),
        ("reconnect_delay_s", -1, "reconnect_delay_s"),
        ("startup_timeout_s", 0, "startup_timeout_s"),
        ("sample_timeout_s", 0, "sample_timeout_s"),
        ("queue_size", 0, "queue_size"),
    ],
)
def test_transport_limits_are_validated(
    field: str,
    value: object,
    message: str,
) -> None:
    transport = {field: value}
    with pytest.raises(ValueError, match=message):
        config_from_dict(
            {
                "room_id": "room_a",
                "device_id": "pi5-a",
                "transport": transport,
            }
        )


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
