from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tomllib

import pytest

from study_space_hardware.bootstrap import build_esp32_hub_drivers
from study_space_hardware.clock import ManualClock
from study_space_hardware.config import config_from_dict, load_config
from study_space_hardware.drivers.remote_sound import RemoteSoundFeatureDriver


PROJECT_ROOT = Path(__file__).parents[1]
EXAMPLE_CONFIG = PROJECT_ROOT / "config/example.yaml"
REAL_CONFIG = PROJECT_ROOT / "config/real.example.yaml"
ESP32_HUB_CONFIG = PROJECT_ROOT / "config/esp32-hub.example.yaml"
WINDOWS_MIC_CONFIG = (
    PROJECT_ROOT / "config/esp32-hub-windows-mic.example.yaml"
)


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
    assert config.transport.queue_size == 64
    assert config.sensors["thermal"].sample_rate_hz == 2
    assert "port" not in config.sensors["radar"].options
    assert config.sensors["radar"].enabled is False
    assert config.sensors["climate"].sample_rate_hz == 0.5


def test_windows_microphone_example_keeps_receiver_on_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "ESP32_HUB_PORT",
        "/dev/serial/by-id/usb-esp32-test",
    )
    config = load_config(WINDOWS_MIC_CONFIG)

    assert config.sensors["sound"].options["driver"] == "remote_feature"
    assert config.sensors["sound"].sample_rate_hz == 1
    assert config.sensors["sound"].options["listen_host"] == "127.0.0.1"
    assert config.sensors["sound"].options["token_env"] == (
        "PSSA_REMOTE_SOUND_TOKEN"
    )


def test_windows_microphone_config_builds_remote_driver_without_opening_audio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "ESP32_HUB_PORT",
        "/dev/serial/by-id/usb-esp32-test",
    )
    monkeypatch.setenv(
        "PSSA_REMOTE_SOUND_TOKEN",
        "test-token-that-is-longer-than-24-characters",
    )
    config = load_config(WINDOWS_MIC_CONFIG)

    drivers = build_esp32_hub_drivers(config, ManualClock())

    assert isinstance(drivers["sound"], RemoteSoundFeatureDriver)
    assert set(drivers) == {"thermal", "sound", "light", "climate"}


def test_windows_microphone_driver_requires_runtime_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "ESP32_HUB_PORT",
        "/dev/serial/by-id/usb-esp32-test",
    )
    monkeypatch.delenv("PSSA_REMOTE_SOUND_TOKEN", raising=False)
    config = load_config(WINDOWS_MIC_CONFIG)

    with pytest.raises(ValueError, match="bearer token environment"):
        build_esp32_hub_drivers(config, ManualClock())


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
